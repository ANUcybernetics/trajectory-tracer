# TODO

- persist all the PD results to disk

- do clustering (with optional dimensionality reduction), with some "timeline"
  vis

- statistical tests on PE across different networks, prompts, seeds, and
  embedding models

- bisect to see why BLIP is failing

- use the dummy embeddings in the final analysis as a control, perhaps with a
  slightly more sophisticated "random walk" scheme

- visualise the time taken for the various different invocations

- run the tests in GitHub actions

- batch the genai models as well (embedding ones already done)

- store the loop_length in the invocation (maybe)

- load dfs directly from the databases (because polars can do that, but the
  calculated properties like loop_length become a PITA)

- write an orphans (or some other validation that the run is all there)
  property/method for Run. Or maybe just a cleanup function
