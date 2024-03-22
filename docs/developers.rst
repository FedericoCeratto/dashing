Development
-----------

``dashing`` welcomes all contributions.

Testing
=======

We use ``pytest`` for the test suite, ``pyte`` to emulate a terminal, and ``pexpect`` to spawn a process and communicate
with the emulated terminal per test. ``pexpect`` does not fully support Windows, so the test suite can only run on WSL
for Windows users.

You can run the testsuite simply by running::

   pytest