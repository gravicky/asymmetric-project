'''
This is an autoscalar I had created for queue length bases scaling of celery workers, for an old project of mine
Its one more tool in a group, aiding in scalability
'''

import os
import time
import json
import logging
import signal
import sys
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

import requests
import kubernetes
from kubernetes.client.rest import ApiException

from omf_backend.constants import config
from omf_worker.worker import app


@dataclass
class ScalingConfig:
    """Configuration for the scaler"""
    threshold: int
    min_replicas: int
    max_replicas: int
    check_interval: int
    scale_up_cooldown: int
    scale_down_cooldown: int
    deployment_name: str
    queue_name: str
    scale_up_factor: float = 1.0
    scale_down_factor: float = 1.0
    grace_period_seconds: int = 30
    
    @classmethod
    def from_env(cls) -> 'ScalingConfig':
        """Load configuration from environment variables"""
        try:
            return cls(
                threshold=int(os.getenv('THRESHOLD', 6)),
                min_replicas=int(os.getenv('MIN_REPLICAS', 3)),
                max_replicas=int(os.getenv('MAX_REPLICAS', 10)),
                check_interval=int(os.getenv('CHECK_INTERVAL', 5)),
                scale_up_cooldown=int(os.getenv('SCALE_UP_COOLDOWN', 5)),
                scale_down_cooldown=int(os.getenv('SCALE_DOWN_COOLDOWN', 60)),
                deployment_name=os.getenv('DEPLOYMENT_NAME'),
                queue_name=os.getenv('QUEUE_NAME'),
                scale_up_factor=float(os.getenv('SCALE_UP_FACTOR', 1.0)),
                scale_down_factor=float(os.getenv('SCALE_DOWN_FACTOR', 1.0)),
                grace_period_seconds=int(os.getenv('GRACE_PERIOD_SECONDS', 30))
            )
        except (ValueError, TypeError) as e:
            raise RuntimeError(f"Invalid configuration: {e}")
    
    def validate(self) -> None:
        """Validate configuration values"""
        if not self.deployment_name:
            raise ValueError("DEPLOYMENT_NAME is required")
        if not self.queue_name:
            raise ValueError("QUEUE_NAME is required")
        if self.min_replicas < 1:
            raise ValueError("MIN_REPLICAS must be at least 1")
        if self.max_replicas < self.min_replicas:
            raise ValueError("MAX_REPLICAS must be greater than or equal to MIN_REPLICAS")
        if self.threshold < 1:
            raise ValueError("THRESHOLD must be at least 1")


class CeleryScaler:
    def __init__(self):
        self.last_scale_up_time = 0
        self.last_scale_down_time = 0
        self.shutdown_requested = False
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
        # Initialize Kubernetes client
        try:
            kubernetes.config.load_incluster_config()
            self.apps_v1 = kubernetes.client.AppsV1Api()
            self.core_v1 = kubernetes.client.CoreV1Api()
        except Exception as e:
            self.logger.error(f"Failed to initialize Kubernetes client: {e}")
            raise
        
        self.namespace = self._get_current_namespace()
        self.scaling_config = ScalingConfig.from_env()
        self.scaling_config.validate()
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        self.logger.info(f"Initialized scaler for deployment '{self.scaling_config.deployment_name}' "
                        f"in namespace '{self.namespace}'")
        
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.shutdown_requested = True
        
    def _get_current_namespace(self) -> str:
        """Get the current Kubernetes namespace"""
        try:
            with open('/var/run/secrets/kubernetes.io/serviceaccount/namespace', 'r') as f:
                return f.read().strip()
        except Exception as e:
            self.logger.error(f"Failed to read namespace from serviceaccount file: {e}")
            # Fallback to environment variable or default
            namespace = os.getenv('KUBERNETES_NAMESPACE', 'default')
            self.logger.warning(f"Using fallback namespace: {namespace}")
            return namespace
    
    def get_celery_worker_pods(self, deployment_name: str) -> List[Any]:
        """Get all running pods for a Celery worker deployment"""
        try:
            deployment = self.apps_v1.read_namespaced_deployment(
                name=deployment_name, 
                namespace=self.namespace
            )
            
            if not deployment.spec.selector.match_labels:
                self.logger.warning(f"No match labels found for deployment {deployment_name}")
                return []
            
            label_selector = ','.join([
                f"{k}={v}" for k, v in deployment.spec.selector.match_labels.items()
            ])
            
            pods = self.core_v1.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=label_selector
            )
            
            running_pods = [
                pod for pod in pods.items 
                if pod.status.phase == 'Running' and 
                pod.metadata.deletion_timestamp is None
            ]
            
            self.logger.debug(f"Found {len(running_pods)} running pods for deployment {deployment_name}")
            return running_pods
            
        except ApiException as e:
            self.logger.error(f"Kubernetes API error getting worker pods: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Unexpected error getting worker pods: {e}")
            return []
    
    def is_pod_idle(self, pod: Any) -> bool:
        """Check if a pod is idle (no active tasks)"""
        try:
            pod_name = pod.metadata.name
            inspect = app.control.inspect()
            
            # Check if inspect is available
            if not inspect:
                self.logger.warning("Celery inspect not available")
                return False
            
            # Get active tasks
            active_tasks = inspect.active()
            
            if not active_tasks:
                self.logger.debug(f"No active tasks data available for pod {pod_name}")
                return False
            
            # Check for tasks on this specific worker
            worker_name = f"celery@{pod_name}"
            
            if worker_name in active_tasks:
                task_count = len(active_tasks[worker_name])
                self.logger.debug(f"Pod {pod_name} has {task_count} active tasks")
                return task_count == 0
            else:
                # Worker not found in active tasks - might be idle or disconnected
                self.logger.debug(f"Worker {worker_name} not found in active tasks")
                return True
                
        except Exception as e:
            self.logger.error(f"Error checking tasks for pod {pod_name}: {e}")
            # On error, assume pod is busy to be safe
            return False
    
    def delete_idle_pods(self, deployment_name: str, target_replicas: int) -> int:
        """Delete idle pods to reach target replica count"""
        try:
            pods = self.get_celery_worker_pods(deployment_name)
            current_count = len(pods)
            
            if current_count <= target_replicas:
                self.logger.info(f"Already at or below target replicas ({current_count} <= {target_replicas})")
                return current_count
            
            pods_to_remove = current_count - target_replicas
            self.logger.info(f"Need to remove {pods_to_remove} pods to reach target of {target_replicas}")
            
            # Sort by creation time (newest first) to remove newer pods first
            pods.sort(key=lambda p: p.metadata.creation_timestamp, reverse=True)
            
            removed_count = 0
            for pod in pods:
                if removed_count >= pods_to_remove:
                    break
                
                if self.is_pod_idle(pod):
                    try:
                        self.logger.info(f"Removing idle pod: {pod.metadata.name}")
                        self.core_v1.delete_namespaced_pod(
                            name=pod.metadata.name,
                            namespace=self.namespace,
                            grace_period_seconds=self.scaling_config.grace_period_seconds
                        )
                        removed_count += 1
                    except ApiException as e:
                        self.logger.error(f"Kubernetes API error deleting pod {pod.metadata.name}: {e}")
                    except Exception as e:
                        self.logger.error(f"Unexpected error deleting pod {pod.metadata.name}: {e}")
                else:
                    self.logger.info(f"Pod {pod.metadata.name} is busy, skipping")
            
            final_count = current_count - removed_count
            self.logger.info(f"Removed {removed_count} pods, expected final count: {final_count}")
            return final_count
            
        except Exception as e:
            self.logger.error(f"Error in delete_idle_pods: {e}")
            return self.get_current_replicas(deployment_name) or 0
    
    def get_current_replicas(self, deployment_name: str) -> Optional[int]:
        """Get current replica count for deployment"""
        try:
            deployment = self.apps_v1.read_namespaced_deployment(
                name=deployment_name, 
                namespace=self.namespace
            )
            return deployment.spec.replicas
        except ApiException as e:
            self.logger.error(f"Kubernetes API error getting current replicas: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error getting current replicas: {e}")
            return None
    
    def scale_up_deployment(self, deployment_name: str, replicas: int) -> bool:
        """Scale up deployment to specified replica count"""
        try:
            self.apps_v1.patch_namespaced_deployment_scale(
                name=deployment_name,
                namespace=self.namespace,
                body={'spec': {'replicas': replicas}}
            )
            self.logger.info(f"Scaled up {deployment_name} to {replicas} replicas")
            return True
        except ApiException as e:
            self.logger.error(f"Kubernetes API error scaling up deployment: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error scaling up deployment: {e}")
            return False
    
    def graceful_scale_down(self, deployment_name: str, target_replicas: int) -> int:
        """Gracefully scale down deployment by removing idle pods first"""
        actual_count = self.delete_idle_pods(deployment_name, target_replicas)
        
        # Update deployment spec to match actual count
        try:
            self.apps_v1.patch_namespaced_deployment_scale(
                name=deployment_name,
                namespace=self.namespace,
                body={'spec': {'replicas': actual_count}}
            )
            self.logger.info(f"Updated deployment spec to {actual_count} replicas")
        except ApiException as e:
            self.logger.error(f"Kubernetes API error updating deployment spec: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error updating deployment spec: {e}")
        
        return actual_count
    
    def get_queue_length(self, queue_name: str) -> int:
        """Get the number of ready messages in the queue"""
        try:
            url = (f"http://{config.broker_configuration.host}:{config.broker_configuration.management_port}/api/queues/%2F/{queue_name}")
            
            response = requests.get(
                url,
                auth=(config.broker_configuration.user, config.broker_configuration.password),
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Only care about ready messages (pending tasks)
            ready_messages = data.get('messages_ready', 0)
            
            self.logger.debug(f"Queue {queue_name} has {ready_messages} ready messages")
            return ready_messages
            
        except requests.RequestException as e:
            self.logger.error(f"Request error getting queue length: {e}")
            return 0
        except (ValueError, KeyError) as e:
            self.logger.error(f"Error parsing queue data: {e}")
            return 0
        except Exception as e:
            self.logger.error(f"Unexpected error getting queue length: {e}")
            return 0
    
    def calculate_target_replicas(self, queue_length: int, current_replicas: int) -> Optional[int]:
        """Calculate target replica count based on queue length and current state"""
        scale_up_threshold = self.scaling_config.threshold
        scale_down_threshold = max(1, self.scaling_config.threshold // 2)
        
        if queue_length > scale_up_threshold:
            # Scale up logic
            scale_factor = max(1, int(queue_length * self.scaling_config.scale_up_factor))
            target = min(current_replicas + scale_factor, self.scaling_config.max_replicas)
            return target if target > current_replicas else None
            
        elif queue_length < scale_down_threshold:
        # elif queue_length < scale_down_threshold or queue_length < current_replicas * 0.25:
            # Scale down logic
            scale_factor = max(1, int(self.scaling_config.scale_down_factor))
            target = max(current_replicas - scale_factor, self.scaling_config.min_replicas)
            return target if target < current_replicas else None
        
        return None
    
    def run_scaling_loop(self):
        """Main scaling loop"""
        self.logger.info("Starting scaling loop...")
        
        while not self.shutdown_requested:
            try:
                # Get current state
                queue_length = self.get_queue_length(self.scaling_config.queue_name)
                current_replicas = self.get_current_replicas(self.scaling_config.deployment_name)
                
                if current_replicas is None:
                    self.logger.warning("Could not get current replicas, skipping this cycle")
                    time.sleep(self.scaling_config.check_interval)
                    continue
                
                current_time = time.time()
                
                # Calculate target replicas
                target_replicas = self.calculate_target_replicas(queue_length, current_replicas)
                
                if target_replicas is None:
                    self.logger.debug(f"No scaling needed - Queue: {queue_length}, "
                                    f"Replicas: {current_replicas}, Threshold: {self.scaling_config.threshold}")
                elif target_replicas > current_replicas:
                    # Scale up
                    if current_time - self.last_scale_up_time >= self.scaling_config.scale_up_cooldown:
                        self.logger.info(f"Scaling up from {current_replicas} to {target_replicas} "
                                       f"(queue length: {queue_length})")
                        if self.scale_up_deployment(self.scaling_config.deployment_name, target_replicas):
                            self.last_scale_up_time = current_time
                    else:
                        remaining_cooldown = self.scaling_config.scale_up_cooldown - (current_time - self.last_scale_up_time)
                        self.logger.debug(f"Scale up on cooldown, {remaining_cooldown:.1f}s remaining")
                        
                elif target_replicas < current_replicas:
                    # Scale down
                    if current_time - self.last_scale_down_time >= self.scaling_config.scale_down_cooldown:
                        self.logger.info(f"Scaling down from {current_replicas} to {target_replicas} "
                                       f"(queue length: {queue_length})")
                        actual_replicas = self.graceful_scale_down(self.scaling_config.deployment_name, target_replicas)
                        if actual_replicas < current_replicas:
                            self.last_scale_down_time = current_time
                    else:
                        remaining_cooldown = self.scaling_config.scale_down_cooldown - (current_time - self.last_scale_down_time)
                        self.logger.debug(f"Scale down on cooldown, {remaining_cooldown:.1f}s remaining")
                
            except Exception as e:
                self.logger.error(f"Error in scaling loop: {e}")
                time.sleep(min(60, self.scaling_config.check_interval * 2))
                continue
                
            time.sleep(self.scaling_config.check_interval)
        
        self.logger.info("Scaling loop stopped gracefully")


def main():
    try:
        scaler = CeleryScaler()
        scaler.run_scaling_loop()
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()