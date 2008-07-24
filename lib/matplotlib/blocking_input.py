"""
This provides several classes used for blocking interaction with figure windows:

:class:`BlockingInput`
    creates a callable object to retrieve events in a blocking way for interactive sessions

:class:`BlockingKeyMouseInput`
    creates a callable object to retrieve key or mouse clicks in a blocking way for interactive sessions.
    Note: Subclass of BlockingInput. Used by waitforbuttonpress

:class:`BlockingMouseInput`
    creates a callable object to retrieve mouse clicks in a blocking way for interactive sessions.
    Note: Subclass of BlockingInput.  Used by ginput

:class:`BlockingContourLabeler`
    creates a callable object to retrieve mouse clicks in a blocking way that will then be used to place labels on a ContourSet
    Note: Subclass of BlockingMouseInput.  Used by clabel
"""

import time
import numpy as np

from matplotlib import path, verbose
from matplotlib.cbook import is_sequence_of_strings

class BlockingInput(object):
    """
    Class that creates a callable object to retrieve events in a
    blocking way.
    """
    def __init__(self, fig, eventslist=()):
        self.fig = fig
        assert is_sequence_of_strings(eventslist), "Requires a sequence of event name strings"
        self.eventslist = eventslist

    def on_event(self, event):
        """
        Event handler that will be passed to the current figure to
        retrieve events.
        """
        # Add a new event to list - using a separate function is
        # overkill for the base class, but this is consistent with
        # subclasses
        self.add_event(event)

        verbose.report("Event %i" % len(self.events))

        # This will extract info from events
        self.post_event()

        # Check if we have enough events already
        if len(self.events) >= self.n and self.n > 0:
            self.fig.canvas.stop_event_loop()

    def post_event(self):
        """For baseclass, do nothing but collect events"""
        pass

    def cleanup(self):
        """Disconnect all callbacks"""
        for cb in self.callbacks:
            self.fig.canvas.mpl_disconnect(cb)

        self.callbacks=[]

    def add_event(self,event):
        """For base class, this just appends an event to events."""
        self.events.append(event)

    def pop_event(self,index=-1):
        """
        This removes an event from the event list.  Defaults to
        removing last event, but an index can be supplied.  Note that
        this does not check that there are events, much like the
        normal pop method.  If not events exist, this will throw an
        exception.
        """
        self.events.pop(index)

    def pop(self,index=-1):
        self.pop_event(index)
    pop.__doc__=pop_event.__doc__

    def __call__(self, n=1, timeout=30 ):
        """
        Blocking call to retrieve n events
        """

        assert isinstance(n, int), "Requires an integer argument"
        self.n = n

        self.events = []
        self.callbacks = []

        # Ensure that the figure is shown
        self.fig.show()

        # connect the events to the on_event function call
        for n in self.eventslist:
            self.callbacks.append( self.fig.canvas.mpl_connect(n, self.on_event) )

        try:
            # Start event loop
            self.fig.canvas.start_event_loop(timeout=timeout)
        finally: # Run even on exception like ctrl-c
            # Disconnect the callbacks
            self.cleanup()

        # Return the events in this case
        return self.events

class BlockingMouseInput(BlockingInput):
    """
    Class that creates a callable object to retrieve mouse clicks in a
    blocking way.
    """
    def __init__(self, fig):
        BlockingInput.__init__(self, fig=fig,
                               eventslist=('button_press_event',) )

    def post_event(self):
        """
        This will be called to process events
        """
        assert len(self.events)>0, "No events yet"

        event = self.events[-1]
        button = event.button

        # Using additional methods for each button is a bit overkill
        # for this class, but it allows for easy overloading.  Also,
        # this would make it easy to attach other type of non-mouse
        # events to these "mouse" actions.  For example, the matlab
        # version of ginput also allows you to add points with
        # keyboard clicks.  This could easily be added to this class
        # with relatively minor modification to post_event and
        # __init__.
        if button == 3:
            self.button3(event)
        elif button == 2:
            self.button2(event)
        else:
            self.button1(event)

    def button1( self, event ):
        """
        Will be called for any event involving a button other than
        button 2 or 3.  This will add a click if it is inside axes.
        """
        if event.inaxes:
            self.add_click(event)
        else: # If not a valid click, remove from event list
            BlockingInput.pop(self)

    def button2( self, event ):
        """
        Will be called for any event involving button 2.
        Button 2 ends blocking input.
        """

        # Remove last event just for cleanliness
        BlockingInput.pop(self)

        # This will exit even if not in infinite mode.  This is
        # consistent with matlab and sometimes quite useful, but will
        # require the user to test how many points were actually
        # returned before using data.
        self.fig.canvas.stop_event_loop()

    def button3( self, event ):
        """
        Will be called for any event involving button 3.
        Button 3 removes the last click.
        """
        # Remove this last event
        BlockingInput.pop(self)

        # Now remove any existing clicks if possible
        if len(self.events)>0:
            self.pop()

    def add_click(self,event):
        """
        This add the coordinates of an event to the list of clicks
        """
        self.clicks.append((event.xdata,event.ydata))

        verbose.report("input %i: %f,%f" %
                       (len(self.clicks),event.xdata, event.ydata))

        # If desired plot up click
        if self.show_clicks:
            self.marks.extend(
                event.inaxes.plot([event.xdata,], [event.ydata,], 'r+') )
            self.fig.canvas.draw()

    def pop_click(self,index=-1):
        """
        This removes a click from the list of clicks.  Defaults to
        removing the last click.
        """
        self.clicks.pop(index)

        if self.show_clicks:
            mark = self.marks.pop(index)
            mark.remove()
            self.fig.canvas.draw()

    def pop(self,index=-1):
        """
        This removes a click and the associated event from the object.
        Defaults to removing the last click, but any index can be
        supplied.
        """
        self.pop_click(index)
        BlockingInput.pop(self,index)

    def cleanup(self):
        # clean the figure
        if self.show_clicks:
            for mark in self.marks:
                mark.remove()
            self.marks = []
            self.fig.canvas.draw()

        # Call base class to remove callbacks
        BlockingInput.cleanup(self)

    def __call__(self, n=1, timeout=30, show_clicks=True):
        """
        Blocking call to retrieve n coordinate pairs through mouse
        clicks.
        """
        self.show_clicks = show_clicks
        self.clicks      = []
        self.marks       = []
        BlockingInput.__call__(self,n=n,timeout=timeout)

        return self.clicks

class BlockingContourLabeler( BlockingMouseInput ):
    """
    Class that creates a callable object that uses mouse clicks on a
    figure window to place contour labels.
    """
    def __init__(self,cs):
        self.cs = cs
        BlockingMouseInput.__init__(self, fig=cs.ax.figure )

    def button1(self,event):
        """
        This will be called if an event involving a button other than
        2 or 3 occcurs.  This will add a label to a contour.
        """

        # Shorthand
        cs = self.cs

        if event.inaxes == cs.ax:
            conmin,segmin,imin,xmin,ymin = cs.find_nearest_contour(
                event.x, event.y, cs.labelIndiceList)[:5]

            # Get index of nearest level in subset of levels used for labeling
            lmin = cs.labelIndiceList.index(conmin)

            # Coordinates of contour
            paths = cs.collections[conmin].get_paths()
            lc = paths[segmin].vertices

            # In pixel/screen space
            slc = cs.ax.transData.transform(lc)

            # Get label width for rotating labels and breaking contours
            lw = cs.get_label_width(cs.labelLevelList[lmin],
                                    cs.labelFmt, cs.labelFontSizeList[lmin])

            """
            # requires python 2.5
            # Figure out label rotation.
            rotation,nlc = cs.calc_label_rot_and_inline(
                slc, imin, lw, lc if self.inline else [],
                self.inline_spacing )
            """
            # Figure out label rotation.
            if self.inline: lcarg = lc
            else: lcarg = None
            rotation,nlc = cs.calc_label_rot_and_inline(
                slc, imin, lw, lcarg,
                self.inline_spacing )

            cs.add_label(xmin,ymin,rotation,cs.labelLevelList[lmin],
                         cs.labelCValueList[lmin])

            if self.inline:
                # Remove old, not looping over paths so we can do this up front
                paths.pop(segmin)

                # Add paths if not empty or single point
                for n in nlc:
                    if len(n)>1:
                        paths.append( path.Path(n) )

            self.fig.canvas.draw()
        else: # Remove event if not valid
            BlockingInput.pop(self)

    def button3(self,event):
        """
        This will be called if button 3 is clicked.  This will remove
        a label if not in inline mode.  Unfortunately, if one is doing
        inline labels, then there is currently no way to fix the
        broken contour - once humpty-dumpty is broken, he can't be put
        back together.  In inline mode, this does nothing.
        """
        # Remove this last event - not too important for clabel use
        # since clabel normally doesn't have a maximum number of
        # events, but best for cleanliness sake.
        BlockingInput.pop(self)

        if self.inline:
            pass
        else:
            self.cs.pop_label()
            self.cs.ax.figure.canvas.draw()

    def __call__(self,inline,inline_spacing=5,n=-1,timeout=-1):
        self.inline=inline
        self.inline_spacing=inline_spacing

        BlockingMouseInput.__call__(self,n=n,timeout=timeout,
                                    show_clicks=False)

class BlockingKeyMouseInput(BlockingInput):
    """
    Class that creates a callable object to retrieve a single mouse or
    keyboard click
    """
    def __init__(self, fig):
        BlockingInput.__init__(self, fig=fig, eventslist=('button_press_event','key_press_event') )

    def post_event(self):
        """
        Determines if it is a key event
        """
        assert len(self.events)>0, "No events yet"

        self.keyormouse = self.events[-1].name == 'key_press_event'

    def __call__(self, timeout=30):
        """
        Blocking call to retrieve a single mouse or key click
        Returns True if key click, False if mouse, or None if timeout
        """
        self.keyormouse = None
        BlockingInput.__call__(self,n=1,timeout=timeout)

        return self.keyormouse
