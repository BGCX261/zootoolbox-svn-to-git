from wx import *


BLUE_MENU = 49, 106, 197

class MenuCtrl(PyControl):
	_MIN_SIZE = 50, 19

	def __init__( self, parent, label='Menu', id=ID_ANY, pos=DefaultPosition, size=_MIN_SIZE, style=0 ):
		PyControl.__init__( self, parent, id, pos, size, style | NO_BORDER )
		self.SetBackgroundStyle( BG_STYLE_CUSTOM )

		self._hover = False
		self._menu = Menu()
		self._cb = None
		self._initialColour = self.GetBackgroundColour()
		self._borderColour = BLACK
		self._textColour = BLACK

		self.SetLabel( label )
		self.SetInitialSize( size )
		self.InheritAttributes()

		#deal with size
		clsMin = self.__class__._MIN_SIZE
		self._MIN_SIZE = ( max( size[ 0 ], clsMin[ 0 ] ), max( size[ 1 ], clsMin[ 1 ] ) )

		self.Bind( EVT_ENTER_WINDOW, self.OnEnter )
		self.Bind( EVT_LEAVE_WINDOW, self.OnLeave )
		self.Bind( EVT_LEFT_DOWN, self.OnClick )

		self.Bind( EVT_PAINT, self.OnPaint )
		self.Bind( EVT_ERASE_BACKGROUND, self.OnErase )
		self.Bind( EVT_SIZE, self.OnSize )
	def DoGetBestSize( self ):
		dc = ClientDC( self )
		dc.SetFont( self.GetFont() )

		width, height = dc.GetTextExtent( self.GetLabel() )

		_min, _max = self._MIN_SIZE
		width = max( _min, width )
		height = max( _max, height )

		#add a sinlge pixel border
		width += 2

		best = Size( width, height )
		self.CacheBestSize( best )

		return best
	def Draw( self, dc=None ):
		if dc is None:
			dc = BufferedDC( ClientDC( self ) )

		if self.IsEnabled():
			if self._hover:
				dc.SetTextForeground( WHITE )
				dc.SetBrush( Brush( BLUE_MENU ) )
			else:
				dc.SetTextForeground( self._textColour )
				dc.SetBrush( Brush( self.GetBackgroundColour() ) )
		else:
			dc.SetBrush( Brush( self.GetBackgroundColour() ) )
			dc.SetTextForeground( SystemSettings.GetColour( SYS_COLOUR_GRAYTEXT ) )

		#set the font before querying any text related data
		dc.SetFont( self.GetFont() )
		w, h = self.GetClientSize()

		#draw the outline
		dc.SetPen( Pen( self._borderColour ) )
		dc.DrawRectangle( 0, 0, w, h )

		#draw the label
		txW, txH = dc.GetTextExtent( self.GetLabel() )
		txX, txY = (w / 2.0) - (txW / 2.0), (h / 2.0) - (txH / 2.0) + 1

		dc.DrawText( self.GetLabel(), txX, txY )

	### EVENT HANDLERS ###
	def OnEnter( self, event ):
		self._hover = True
		self.Refresh()
	def OnLeave( self, event ):
		self._hover = False
		self.Refresh()
	def OnClick( self, event ):
		selfRect = self.GetRect()
		menuPos = 0, selfRect[ 3 ]

		if callable( self._cb ):
			self._cb( self )

		self.PopupMenu( self._menu, menuPos )
	def OnPaint( self, event ):
		self.Draw( BufferedPaintDC( self ) )
	def OnErase( self, event ): pass
	def OnSize( self, event ):
		event.Skip()
		self.Refresh()


class CrashTest(Panel):
	count = 0

	def __init__( self, parent ):
		Panel.__init__( self, parent )

		sz = BoxSizer( VERTICAL )
		self.SetSizer( sz )

		self.populate()

		self.Bind( EVT_TIMER, self.on_rebuild )

		self.timer = Timer( self )
		self.timer.Start( 50 )
	def populate( self ):
		sz = self.GetSizer()
		sz.Clear( True )

		maxRange = 1000

		widgetClass = MenuCtrl
		#widgetClass = Button  ##uncomment this line to use buttons instead of the above custom control - no memory leakage anymore!

		hsz = BoxSizer( HORIZONTAL )
		hsz.Add( widgetClass( self, label='im a horizontals!' ), 1, EXPAND )
		hsz.Add( widgetClass( self, label='horizontals TOOO!' ), 1, EXPAND )
		#hsz.Add( sliders.TimeSlider( self, self.count % maxRange, (0, maxRange) ), 1, EXPAND )

		sz.Add( widgetClass( self, label='this is menu 1' ), 0, EXPAND )
		sz.Add( widgetClass( self, label='another menu is this' ), 1, EXPAND )
		sz.Add( widgetClass( self, label='count = %d!!!!' % self.count ), 0, EXPAND )
		sz.Add( hsz, 1, EXPAND )

		self.Layout()
	def on_rebuild( self, event ):
		CrashTest.count += 1
		self.populate()


app = App()
f = Frame( None )
p = CrashTest( f )
f.Show()
app.MainLoop()