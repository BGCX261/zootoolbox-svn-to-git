from filesystem import Path
import subprocess
import time
import re
import os


class P4Exception(Exception): pass


class P4Path(Path):
	TIMEOUT_PERIOD = 5
	USE_P4 = True

	def __new__( cls, path='', caseMatters=None, envDict=None ):
		pass
	def __init__( self, path='', caseMatters=None, envDict=None ):
		pass


class P4Output(dict):
	EXIT_PREFIX = 'exit:'
	ERROR_PREFIX = 'error:'

	#
	START_DIGITS = re.compile( '(^[0-9]+)(.*)' )
	END_DIGITS = re.compile( '(.*)([0-9]+$)' )

	def __init__( self, outStr, keysColonDelimited=False ):
		EXIT_PREFIX = P4Output.EXIT_PREFIX
		ERROR_PREFIX = P4Output.ERROR_PREFIX
		self.errors = []

		if isinstance( outStr, basestring ):
			lines = outStr.split( '\n' )
		elif isinstance( outStr, (list, tuple) ):
			lines = outStr
		else:
			print outStr
			raise P4Exception( "unsupported type (%s) given to %s" % (type( outStr ), self.__class__.__name__) )

		delimiter = ':' if keysColonDelimited else ' '
		for line in lines:
			line = line.strip()

			if not line:
				continue

			if line.startswith( EXIT_PREFIX ):
				break

			if line.startswith( ERROR_PREFIX ):
				self.errors.append( line )
				continue

			idx = line.find( ':' )
			if idx == -1:
				continue

			line = line[ idx + 1: ].strip()
			idx = line.find( delimiter )
			if idx == -1:
				prefix = line
				data = True
			else:
				prefix = line[ :idx ].strip()
				data = line[ idx + 1: ].strip()
				if data.isdigit():
					data = int( data )

			if keysColonDelimited:
				prefix = ''.join( [ s.capitalize() if n else s for n, s in enumerate( prefix.lower().split() ) ] )
			else:
				prefix = prefix[ 0 ].lower() + prefix[ 1: ]

			self[ prefix ] = data

		#finally, if there are prefixes which have a numeral at the end, strip it and pack the data into a list
		multiKeys = {}
		for k in self.keys():
			m = self.END_DIGITS.search( k )
			if m is None:
				continue

			prefix, idx = m.groups()
			idx = int( idx )

			data = self.pop( k )
			try:
				multiKeys[ prefix ].append( (idx, data) )
			except KeyError:
				multiKeys[ prefix ] = [ (idx, data) ]

		for prefix, dataList in multiKeys.iteritems():
			try:
				self.pop( prefix )
			except KeyError: pass

			dataList.sort()
			self[ prefix ] = [ d[ 1 ] for d in dataList ]
	def __getattr__( self, attr ):
		return self[ attr ]
	def asStr( self ):
		return '\n'.join( '%s:  %s' % items for items in self.iteritems() )


def _p4run( *args ):
	if not P4Path.USE_P4:
		return False

	cmdStr = 'p4 '+ ' '.join( map( str, args ) )
	print cmdStr
	try:
		p4Proc = subprocess.Popen( cmdStr, stdout=subprocess.PIPE, stderr=subprocess.PIPE )
	except OSError:
		P4Path.USE_P4 = False
		return False

	startTime = time.clock()
	stdoutAccum = []
	stderrAccum = []
	while True:
		ret = p4Proc.poll()
		newStdout = p4Proc.stdout.readlines()
		newStderr = p4Proc.stderr.readlines()

		stdoutAccum += newStdout
		stderrAccum += newStderr

		#if the proc has terminated, deal with returning appropriate data
		if ret is not None:
			return stdoutAccum + stderrAccum

		#if there has been new output, the proc is still alive so reset counters
		if newStderr or newStdout:
			startTime = time.clock()

		#make sure we haven't timed out
		curTime = time.clock()
		if curTime - startTime > P4Path.TIMEOUT_PERIOD:
			return False


def p4run( *args, **kwargs ):
	ret = _p4run( *args )
	if ret is False:
		return False

	return P4Output( ret, **kwargs )


P4INFO = None
def p4Info():
	global P4INFO

	if P4INFO:
		return P4INFO

	P4INFO = p4run( '-s info', keysColonDelimited=True )

	return P4INFO


class P4Change(dict):
	CHANGE_NUM_INVALID = -1
	CHANGE_NUM_DEFAULT = 0

	def __init__( self ):
		self.change = None
		self.description = None
		self.files = []
		self.actions = []
		self.revisions = []
	def __len__( self ):
		return len( self.files )
	def __iter__( self ):
		return zip( self.files, self.revisions, self.actions )
	@classmethod
	def Create( cls, description, files=None ):

		info = p4Info()
		contents = '''Change:\tnew\n\nClient:\t%s\n\nUser:\t%s\n\nStatus:\tnew\n\nDescription:\n\t%s\n''' % (info.clientName, info.userName, description)

		p4Proc = subprocess.Popen( 'p4 -s change -i', stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE )
		stdout, stderr = p4Proc.communicate( contents )

		if stderr:
			return False

		output = P4Output( stdout, False )
		changeNum = int( P4Output.START_DIGITS.match( output.change ).groups()[ 0 ] )

		new = cls()
		new.description = description
		new.change = changeNum

		if files is not None:
			p4run( 'reopen -c', changeNum, *files )

		return new
	@classmethod
	def FetchByNumber( cls, number ):
		lines = _p4run( '-s', 'describe', number )
		if not lines:
			return None

		change = cls()
		change.change = number

		change.description = ''
		lineIter = iter( lines[ 2: ] )
		try:
			prefix = 'text:'
			PREFIX_LEN = len( prefix )

			line = lineIter.next()
			while line.startswith( prefix ):
				line = line[ PREFIX_LEN: ].lstrip()

				if line.startswith( 'Affected files ...' ):
					break

				change.description += line
				line = lineIter.next()

			prefix = 'info1:'
			PREFIX_LEN = len( prefix )
			while not line.startswith( prefix ):
				line = lineIter.next()

			while line.startswith( prefix ):
				line = line[ PREFIX_LEN: ].lstrip()
				idx = line.rfind( '#' )
				depotFile = Path( line[ :idx ] )

				revAndAct = line[ idx + 1: ].split()
				rev = int( revAndAct[ 0 ] )
				act = revAndAct[ 1 ]

				change.files.append( depotFile )
				change.actions.append( act )
				change.revisions.append( rev )

				line = lineIter.next()
		except StopIteration:
			pass

		return change
	@classmethod
	def FetchByDescription( cls, description, createIfNotFound=False ):
		'''
		fetches a changelist based on a given description from the list of pending changelists
		'''
		cleanDesc = ''.join( [ s.strip() for s in description.lower().strip().split( '\n' ) ] )
		for change in cls.IterPending():
			thisDesc = ''.join( [ s.strip() for s in change.description.lower().strip().split( '\n' ) ] )
			if thisDesc == cleanDesc:
				return change

		if createIfNotFound:
			return cls.Create( description )
	@classmethod
	def IterPending( cls ):
		'''
		iterates over pending changelists
		'''
		info = p4Info()
		for line in _p4run( 'changes -u %s -s pending -c %s' % (info.userName, info.clientName) ):
			toks = line.split()
			changeNum = int( toks[ 1 ] )

			yield cls.FetchByNumber( changeNum )


DEFAULT_CHANGE = 'default'

class P4File(Path):
	'''
	provides a more convenient way of interfacing with perforce.  NOTE: where appropriate all actions
	are added to the changelist with the description DEFAULT_CHANGE
	'''
	DEFAULT_CHANGE = DEFAULT_CHANGE

	BINARY = 'binary'
	XBINARY = 'xbinary'

	TIMEOUT_PERIOD = 5
	USE_P4 = True

	#def __init__( self, path='', caseMatters=None, envDict=None ):
		#Path.__init__( self, path, caseMatters, envDict )
		#self.
	def run( self, *args, **kwargs ):
		return p4run( *args, **kwargs )
	def getFile( self, f=None ):
		if f is None:
			return self

		return Path( f )
	def getStatus( self, f=None ):
		'''
		returns the status dictionary for the instance.  if the file isn't managed by perforce,
		None is returned
		'''
		if not self.USE_P4:
			return None

		f = self.getFile( f )
		try:
			return self.run( '-s fstat', f )
		except Exception: return None
	def isManaged( self, f=None ):
		'''
		returns True if the file is managed by perforce, otherwise False
		'''
		if not self.USE_P4:
			return False

		f = self.getFile( f )
		stat = self.getStatus( f )
		if stat:
			#if the file IS managed - only return true if the head action isn't delete - which effectively means the file
			#ISN'T managed...
			try:
				return stat[ 'headAction' ] != 'delete'
			except KeyError:
				#this can happen if the file is a new file and is opened for add
				return True
		return False
	managed = isManaged
	def isUnderClient( self, f=None ):
		'''
		returns whether the file is in the client's root
		'''
		if not self.USE_P4:
			return False

		f = self.getFile( f )
		results = self.getStatus()
		if not results:
			phrases = [ "not in client view", "not under client's root" ]
			for e in results.errors:
				for ph in phrases:
					if ph in e: return False

		return True
	def getAction( self, f=None ):
		'''
		returns the head "action" of the file - if the file isn't in perforce None is returned...
		'''
		if not self.USE_P4:
			return None

		f = self.getFile( f )
		data = self.getStatus( f )

		try:
			return data.get( 'action', None )
		except AttributeError: return None
	action = property( getAction )
	def getHaveHead( self, f=None ):
		if not self.USE_P4:
			return False

		f = self.getFile( f )
		data = self.getStatus( f )

		try:
			return int( data[ 'haveRev' ] ), int( data[ 'headRev' ] )
		except (AttributeError, TypeError, KeyError):
			return None, None
	def isEdit( self, f=None ):
		if not self.USE_P4:
			return False

		f = self.getFile( f )

		editActions = [ 'add', 'edit' ]
		action = self.getAction( f )

		#if the action is none, the file may not be managed - check
		if action is None:
			if not self.getStatus( f ):
				return None

		return action in editActions
	def isLatest( self, f=None ):
		'''
		returns True if the user has the latest version of the file, otherwise False
		'''

		#if no p4 integration, always say everything is the latest to prevent complaints from tools
		if not self.USE_P4:
			return True

		f = self.getFile( f )
		status = self.getStatus( f )
		if not status:
			return None

		#if there is any action on the file then always return True
		if 'action' in status:
			return True

		#otherwise check revision numbers
		try:
			headRev, haveRev = status[ 'headRev' ], status[ 'haveRev' ]

			return headRev == haveRev
		except KeyError:
			return False
	def editoradd( self, f=None ):
		if not self.USE_P4:
			return False

		f = self.getFile( f )

		#if the file doesn't exist, bail
		if not os.path.exists( f ):
			return False

		action = self.getAction( f )
		if not self.managed( f ):
			return self.run( 'add', '-c', self.getOrCreateChange(), f )
		elif action is None:
			return self.run( 'edit', '-c', self.getOrCreateChange(), f )

		return True
	edit = editoradd
	def add( self, f=None, type=None ):
		if not self.USE_P4:
			return False

		f = self.getFile( f )
		args = [ 'add', '-c', self.getOrCreateChange() ]

		#if the type has been specified, add it to the add args
		if type is not None:
			args += [ '-t', type ]
		args.append( f )

		return self.run( *args )
	def revert( self, f=None ):
		if not self.USE_P4:
			return False

		f = self.getFile( f )

		return self.run( 'revert', f )
	def sync( self, f=None, force=False, rev=None, change=None ):
		'''
		rev can be a negative number - if it is, it works as previous revisions - so rev=-1 syncs to
		the version prior to the headRev.  you can also specify the change number using the change arg.
		if both a rev and a change are specified, the rev is used
		'''
		if not self.USE_P4:
			return False

		f = self.getFile( f )

		#if file is a directory, then we want to sync to the dir
		if os.path.isdir(f):
			f = ('%s/...' % f).replace('//','/')

		if rev is not None:
			if rev == 0: f += '#none'
			elif rev < 0:
				status = self.getStatus()
				headRev = status[ 'headRev' ]
				rev += int( headRev )
				if rev <= 0: rev = 'none'
				f += '#%s' % rev
			else: f += '#%s' % rev
		elif change is not None:
			f += '@%s' % change

		if force: return self.run( '-s sync', '-f', f )
		else: return self.run( '-s sync', f )
	def delete( self, f=None ):
		if not self.USE_P4:
			return False

		f = self.getFile( f )
		action = self.getAction( f )
		if action is None and self.managed( f ):
			return self.run( '-s delete', '-c', self.getOrCreateChange(), f )
	def rename( self, newName, f=None ):
		if not self.USE_P4:
			return False

		f = self.getFile( f )

		try:
			action = self.getAction( f )
			if action is None and self.managed( f ):
				self.run( 'integrate', '-c', self.getOrCreateChange(), f, str( newName ) )
				return self.run( 'delete', '-c', self.getOrCreateChange(), f )
		except Exception: pass
		return False
	def copy( self, newName, f=None ):
		if not self.USE_P4:
			return False

		f = self.getFile( f )
		newName = self.getFile( newName )
		action = self.getAction( f )

		if self.managed( f ):
			return self.run( 'integrate', '-c', self.getOrCreateChange(), f, newName )

		return False
	def submit( self, change=None ):
		if not self.USE_P4:
			return

		if change is None:
			change = self.getChange()

		self.run( 'submit', '-c', change )
	def getChange( self, f=None ):
		if not self.USE_P4:
			return P4Change.CHANGE_NUM_INVALID

		f = self.getFile( f )
		stat = self.getStatus( f )
		try:
			return stat.get( 'change', P4Change.CHANGE_NUM_DEFAULT )
		except (AttributeError, ValueError): return P4Change.CHANGE_NUM_DEFAULT
	def setChange( self, newChange=None, f=None ):
		'''
		sets the changelist the file belongs to. the changelist can be specified as either a changelist
		number, a P4Change object, or a description. if a description is given, the existing pending
		changelists are searched for a matching description.  use 0 for the default changelist.  if
		None is passed, then the changelist as described by self.DEFAULT_CHANGE is used
		'''
		if not self.USE_P4:
			return

		if isinstance( newChange, (int, long) ):
			change = newChange
		elif isinstance( newChange, P4Change ):
			change = newChange.change
		else:
			change = P4Change.FetchByDescription( newChange, True ).change

		f = self.getFile( f )
		self.run( 'reopen', '-c', change, f )
	def getOtherOpen( self, f=None ):
		f = self.getFile( f )
		statusDict = self.getStatus( f )
		try:
			return statusDict[ 'otherOpen' ]
		except (KeyError, TypeError):
			return []
	def getOrCreateChange( self, f=None ):
		'''
		if the file isn't already in a changelist, this will create one.  returns the change number
		'''
		if not self.USE_P4:
			return self.CHANGE_NUM_INVALID

		f = self.getFile( f )
		ch = self.getChange( f )
		if ch == self.CHANGE_NUM_DEFAULT:
			return P4Change.FetchByDescription( self.DEFAULT_CHANGE ).change

		return ch
	def allPaths( self, f=None ):
		'''
		returns all perforce paths for the file (depot path, workspace path and disk path)
		'''
		if not self.USE_P4:
			return None

		f = self.getFile( f )

		dataLine = _p4run( 'where', f )[ 0 ].strip()
		dataLineToSearch = dataLine
		fName = f[ -1 ]
		fNameLen = len( fName )

		if not self.doesCaseMatter():
			dataLineToSearch = dataLine.lower()
			fName = fName.lower()

		#I'm not entirely sure this is bullet-proof...  but basically the return string for this command
		#is a simple space separated string, with three values.  i guess I could try to match //HOSTNAME
		#and the client's depot root to find the start of files, but for now its simply looking for the
		#file name substring three times
		depotNameIdx = dataLineToSearch.find( fName ) + fNameLen
		depotName = P4File( dataLine[ :depotNameIdx ], self.doesCaseMatter() )

		workspaceNameIdx = dataLineToSearch.find( fName, depotNameIdx ) + fNameLen
		workspaceName = P4File( dataLine[ depotNameIdx + 1:workspaceNameIdx ], self.doesCaseMatter() )

		diskNameIdx = dataLineToSearch.find( fName, workspaceNameIdx ) + fNameLen
		diskName = P4File( dataLine[ workspaceNameIdx + 1:diskNameIdx ], self.doesCaseMatter() )

		return depotName, workspaceName, diskName
	def toDepotPath( self, f=None ):
		'''
		returns the depot path to the file
		'''
		if not self.USE_P4:
			return None

		return self.allPaths( f )[ 0 ]
	def toDiskPath( self, f=None ):
		'''
		returns the disk path to a depot file
		'''
		if not self.USE_P4:
			return None

		return self.allPaths( f )[ 2 ]


#print _p4run( '-s fstat //valvegames/l4d/main/game/bin/base.fgd' )
#FROM FSTAT...  FUCK YOU PERFORCE
s='''
info1: depotFile //valvegames/l4d/main/game/bin/base.fgd
info1: clientFile z:/valve/l4d\game\bin\base.fgd
info1: isMapped
info1: headAction edit
info1: headType text
info1: headTime 1252691117
info1: headRev 100
info1: headChange 732580
info1: headModTime 1252689561
info1: haveRev 99
info2: otherOpen0 sergiy@sergiy_l4d_linux
info2: otherAction0 edit
info2: otherChange0 default
info2: otherOpen1 zoid@zoidi7
info2: otherAction1 edit
info2: otherChange1 default
info2: otherOpen 2
exit: 0
'''
#print P4Output( s, False )
print P4File( r'd:\tools\python\cacheDecorators.py' ).getStatus().asStr()
print P4File( r'd:\tools\python\cacheDecorators.py' ).toDepotPath()
#print _p4run( r'-s where d:\tools\python\cacheDecorators.py' )


#end
