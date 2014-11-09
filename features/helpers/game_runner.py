import time
import os
import sys
from Queue import Empty
from multiprocessing import Process, Queue
from test_events import process_events
import coverage
import traceback

class GameRunner(object):

	def __init__(self, mod_path, ini_dir_path):
		self._mod_path = mod_path
		self._ini_dir_path = ini_dir_path
		self._to_proc_queue = Queue()
		self._from_proc_queue = Queue()
		self._process = None

	def __getattr__(self, name):
		return self._stub(name)

	def _stub(self, name):
		return MethodStub(name, self)

	def start(self):
		self._process = Process(
			target=game_main,
			args=(self._to_proc_queue, self._from_proc_queue, self._mod_path, self._ini_dir_path)
		)
		self._process.start()

	def stop(self):
		if self._process:
			self.quit()
			self._process.join()
			self._process = None

	def is_running(self):
		return self._process and self._process.is_alive()

class MethodStub(object):

	def __init__(self, method_name, runner):
		self._method_name = method_name
		self._runner = runner

	def __call__(self, *args, **kwargs):
		result = None
		self._runner._to_proc_queue.put((self._method_name, args, kwargs))
		while self._runner.is_running():
			process_events()
			try:
				result = self._runner._from_proc_queue.get(block=False)
				break
			except Empty:
				pass
		if issubclass(result.__class__, Exception):
			raise result
		return result


def game_main(from_runner_queue, to_runner_queue, mod_path, ini_dir_path):
	cov = coverage.coverage(
		auto_data=True,
		branch=True,
		source=["src"],
		omit=["*CameraNode.py", "*__init__.py"]
	)
	cov.start()

	try:
		service = GameService(from_runner_queue, to_runner_queue)

		base_path = os.path.dirname(os.path.realpath(__file__))

		sys.path.append(os.path.dirname(mod_path))
		sys.path.append(os.path.join(base_path, "fakes"))

		# create directory structure for ini-file
		try:
			os.makedirs(ini_dir_path)
		except:
			pass
		# remove previous ini-file (if one exists)
		try:
			for file_name in os.listdir(ini_dir_path):
				os.remove(os.path.join(ini_dir_path, file_name))
		except:
			pass
		import tessu_mod
		import tessu_utils.ts3
		import tessu_utils.settings
		import tessu_utils.utils
		tessu_utils.ts3._RETRY_TIMEOUT = 1
		tessu_utils.utils.get_ini_dir_path = lambda: ini_dir_path

		tessu_mod.load_mod()

		import BigWorld
		while True:
			if not service.tick():
				break
			BigWorld.tick()
			time.sleep(0.01)
	finally:
		cov.stop()
		cov.save()

class GameService(object):

	def __init__(self, from_queue, to_queue):
		self._from_queue = from_queue
		self._to_queue = to_queue
		self._quit = False
		self._found_log_indexes = []

	def tick(self):
		try:
			call = self._from_queue.get(block=False)
		except:
			call = None
		if call:
			method_name, args, kwargs = call
			try:
				result = getattr(self, method_name)(*args, **kwargs)
			except Exception as error:
				traceback.print_exc()
				result = error
			self._to_queue.put(result)
		return not self._quit

	def quit(self):
		self._quit = True

	def login(self):
		import BigWorld
		import Account
		BigWorld.player(Account.PlayerAccount())

	def enter_battle(self):
		import BigWorld
		import Avatar
		BigWorld.player(Avatar.Avatar())

	def notification_center_has_message(self, message):
		import gui.SystemMessages
		for _ in self._processing_events():
			if message in gui.SystemMessages.messages:
				return True
		return False

	def _processing_events(self, timeout=20):
		import BigWorld
		end_t = time.time() + timeout
		while time.time() < end_t:
			yield
			BigWorld.tick()
			time.sleep(0.01)

	def get_logs(self):
		import debug_utils
		return debug_utils.logs

	def add_player(self, player_name):
		import BigWorld
		if hasattr(BigWorld.player(), "arena"):
			BigWorld.player().arena.add_vehicle(player_name)
		if hasattr(BigWorld.player(), "prebattle"):
			BigWorld.player().prebattle.add_roster(player_name)

	def is_player_speaking(self, player_name):
		import VOIP
		for _ in self._processing_events():
			if VOIP.getVOIPManager().isParticipantTalking(self._get_player_dbid(player_name)):
				return True
		return False

	def is_player_not_speaking(self, player_name):
		import VOIP
		for _ in self._processing_events():
			if not VOIP.getVOIPManager().isParticipantTalking(self._get_player_dbid(player_name)):
				return True
		return False

	def wait_for_log(self, log_message, once=True):
		import debug_utils
		for _ in self._processing_events():
			for index in range(len(debug_utils.logs)):
				if once and index in self._found_log_indexes:
					continue
				log = debug_utils.logs[index]
				if log_message.lower() in log[1].lower():
					self._found_log_indexes.append(index)
					return True
		return False	

	def reload_ini_file(self):
		from tessu_utils.settings import settings
		settings().sync()

	def _get_player_dbid(self, player_name):
		import BigWorld
		if hasattr(BigWorld.player(), "arena"):
			for vehicle_id in BigWorld.player().arena.vehicles:
				vehicle = BigWorld.player().arena.vehicles[vehicle_id]
				if player_name == vehicle["name"]:
					return vehicle["accountDBID"]
		if hasattr(BigWorld.player(), "prebattle"):
			rosters = BigWorld.player().prebattle.rosters
			for roster in rosters:
				for id in rosters[roster]:
					info = rosters[roster][id]
					if player_name == info["name"]:
						return info["dbID"]
		raise RuntimeError("Player {0} doesn't exist".format(player_name))