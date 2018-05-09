import logging
import mido


class Dummy(object):

	def tick(self, tick):
		pass

	def draw(self):
		pass

	def __getitem__(self, i):
		logging.debug("Returning recursive dummy object for key {}".format(i))
		if isinstance(i, int) and i>15:
			raise IndexError
		return self

	def __setitem__(self, i, v):
		pass

	def send(self, *args):
		pass


class Keyboard(object):

	def __init__(self, griode, port_name):
		self.griode = griode
		self.port_name = port_name
		self.grid_name = port_name # FIXME
		self.midi_in = mido.open_input(port_name)
		self.midi_in.callback = self.callback

		self.loopcontroller = Dummy()
		self.notepickers = Dummy()
		self.arpconfigs = Dummy()
		self.surface = {}

	def callback(self, message):
		logging.debug("{} got message {}".format(self, message))
		self.griode.devicechains[message.channel].send(message)
		#self.griode.synth.send(message)

	def tick(self, tick):
		pass