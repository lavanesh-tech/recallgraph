-- Runs once, on first initialization of the data volume.
-- Separate database so integration tests never touch development data.
CREATE DATABASE recallgraph_test;
