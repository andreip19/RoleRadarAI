import os

# All automated tests use an isolated in-memory SQLite database.
# Never allow the test suite to write to the production database.

os.environ["DATABASE_URL"] = "sqlite://"
