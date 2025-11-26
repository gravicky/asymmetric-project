- Move the scoring from being combined in single worker to instead run seperately after each user submits

- Combine all answers of a user to a single document per test

- Modify the db functions/operations to make them more db asynchronous

- Change predictions to use bucketed percentiles + interpolation

- Better auth, using an oidc provider, so that users can login using google, azure AD etc

- Look into multithreading for rank calculation + faster lang?

- Addition of storage for user ip addresses, feeds for anti-cheat?

- add caching wherever required, in leaderboards, user scores for a fixed time

- modify rate limiting, add for other endpoints

- add the custom autoscalar for workers - for computing score

- hashicorp vault 


