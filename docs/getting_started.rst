Getting Started
===============

Setting up a basic application
------------------------------

Dashing lets you create elegantly tiled interfaces for your terminal application user interface (TUI). Create your TUI
by constructing a suitable root :class:`.Tile`. The simplest possible example would be to create a single :class:`.Text` tile:

.. code-block:: python

    from dashing import Text, open_terminal

    ui = Text(text="Hello World, this is dashing!", color=0)

    with open_terminal() as terminal:
        ui.display(terminal)
        input("\nPress Enter to quit")

You should see the Dashing TUI open, display the application, wait for input, and then clean itself up.

.. warning::

  We use color ``0``, black, which might not contrast enough with your terminal's color to be visible! Try another number
  between 0-7 (included) if you don't see anything.


.. admonition:: Note - Terminals
  :class: note

  We use the :func:`.open_terminal` helper to open an underlying Blessed terminal. If you wish to integrate Dashing into
  an existing Blessed application, you can simply pass an existing ``Terminal`` object. Without using a proper Terminal
  context, calls to ``ui.display()`` may leave the user's terminal in a messy state!

The power of Dashing shines when you combine it with an event loop, and make periodic calls to ``ui.display()`` to
update and redraw the screen.

Let's create an application with a title, border, and 2 horizontal gauges that increment decrement for a couple of
seconds:


.. code-block:: python

    from dashing import HGauge, HSplit, Text, open_terminal

    ui = HSplit(
         HGauge(),
         HGauge(val=100),
         border_color=3,
         title="My First App"
    )

    with open_terminal() as terminal:
        for i in range(100):
            ui.items[0].value = i % 101
            ui.items[1].value = (100 - (i % 101))
            ui.display(terminal)
            time.sleep(1 / 25)

As you can see, Dashing added a border and a title around the root tile, and periodically redraws the screen with the
new values.