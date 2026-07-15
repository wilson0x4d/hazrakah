AI Assistant ``SKILL.md``
=========================

The source code repository for this project contains a ``SKILL.md`` that can be used by coding assistants.

Consider adding this to your AGENTS.md / CLAUDE.md or equivalent, this helps avoid wasting token, compute, and time:

.. code:: markdown

    # Library Exploration

    When exploring any library or reference (local, online, or Git), ALWAYS read the `SKILL.md` at the repository root first. It contains the canonical usage patterns and is the source of truth — do not browse `src/` to reverse-engineer API conventions when there is a `SKILL.md` available.


Alternatively you can manually install this to the ``skills/`` directory like you would any other skill, but the prompt snippet above has the value of applying when:

* The agent is exploring the library from site-packages.
* The agent is exploring a repo via HTTP.
* The agent is exploring the repo on disk some other way (such as opencode's ``repos/`` directory).

Hopefully this becomes a common convention, if you're a library author PLEASE consider doing this!
