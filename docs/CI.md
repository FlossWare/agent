# Continuous integration

The `test` workflow runs the package smoke suite on pushes and pull requests.
It installs the project with the development dependencies and executes `pytest -q` on Python 3.11.

Provider credentials are not required for the unit/integration boundary tests; live provider calls remain an explicit dogfood concern.
