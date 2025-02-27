#!/usr/bin/env python3
# Building tool for compiling projects source files (maily c/c++)
# @Author Leonardo Montagner https://github.com/leomonta/Python_cpp_builder
#
# Done: retrive include dirs, libs and args from a file
# Done: compile and link files
# Done: support for debug and optimization compilation, compiler flag and libraries
# Done: retrive target directories for exe, objects, include and source files
# Done: skip compilation or linking if there are no new or modified files
# Done: if error occurs during compilation stop and return 1
# Done: if error occurs during linking stop and return 1
# Done: if a config value is empty prevent double space in cmd agument
# Done: add a type config value for gcc | msvc so i can decide which cmd args to use -> -o | -Fo
# Done: use compiler exec if no linker exec is present
# Done: check for newer version of source files
# Done: multithreaded compiling
# Done: check for newer version of header files (check in every file if that header is included, if it has to be rebuilt)
# Done: add specific linker exec
# Done: error and warning coloring in the console
# Done: support for pre and post script
# Done: support support for any profile name
# Done: implicit empty profile if none is specified
# Done: refactor out global variables (except constants)
# Done: maximum thread amount to run at the same time
# Done: default profile to perform default overrides for each other profile
# TODO: implicit empty configuration if no config file is found
# Done: better argument parsing
# TODO: use a better tool to get the includes off a file
# FIXME: the include chain stops on the first modified include, instead of reporting all of them
# FIXME: exported makefile does not rely on the default profile
# FIXME: the makefile prevent make from detecting if the source files have been modified

import subprocess # execute command on the cmd / bash / whatever
import os         # get directories file names
import json       # parse cpp_builder_config.json
import hashlib    # for calculating hashes
import threading  # for threading, duh
import time       # time.sleep
import sys        # for arguments parsing
import copy       # for deep copy
import typing     # for callable


TEMPLATE = """{
	"compiler": {
		"compiler_style": "gcc",
		"compiler_exe": "gcc",
		"linker_exe": "ld"
	},

	"directories": {
		"project_dir": ".",
		"exe_path_name": "bin/app",
		"include_dirs": [
			"include"
		],
		"source_dirs": [
			"src"
		],
		"temp_dir": "obj"
	},

	"default":
		"compiler_args": "-g3",
		"linker_args": "",
		"libraries_dirs": [
		],
		"libraries_names": [
		],
		"scripts": {
			"pre": "",
			"post": "",
		}

	}
}
"""

HELP = """Usage: cpp_builder.py -p PROFILE [OPTION]
   or: cpp_builder.py [--gen | -e | --help | -h]

general options

  -a                    rebuild the entire project
  -p <profile-name>     utilize the given profile specifies in the config file
  -e                    do not compile and export the `cpp_builder_config` as a Makefile
      --gen             writes in the current directory an empty `cpp_builder_config.json` file
  -n <num-of-threads>   number of parallel threads to execute at the same time, default 12, -1 for as many as compilation units
  -h, --help            print this screen

printing options

	  --skip-empty-reports  do not show reports that are empty
	  --skip-warn-reports   do not show reports that contain only warnings
	  --skip-all-reports    do not show reports

	  --skip-progress       do not show the animations for compiling units
	  --skip-statuses       do not show any status for compiling / done / failed compilations

	  --no-colors           do not use colors for the output, same for compiler reports
"""

CONFIG_FILENAME = "cpp_builder_config.json"
HASH_FILENAME = "files_hash"

DEFAULT_COMPILER = "gcc"

EMPTY_PROFILE = {
 "libraries_names": [],
 "libraries_dirs": [],
 "compiler_args": "",
 "linker_args": "",
 "scripts": {
  "pre": "",
  "post": ""
 }
}

SPINNERS: list[str] = ["|", "/", "-", "\\"]

SOURCE_FILES_EXTENSIONS: list[str] = ["c", "cpp", "cxx", "c++", "cc", "C", "s"]

COMPILER_SPECIFIC_ARGS: list[dict[str]] = [
 {
  "compile_only": "-c",
  "output_compiler": "-o ",
  "output_linker": "-o ",
  "object_extension": "o",
  "include_path": "-I",
  "library_path": "-L",
  "library_name": "-l",
  "force_colors": "-fdiagnostics-color=always",
  "no_colors": "-fdiagnostics-color=always",
 }, {
  "compile_only": "/c",
  "output_compiler": "/Fo",
  "output_linker": "/OUT:",
  "object_extension": "obj",
  "include_path": "/I",
  "library_path": "/LIBPATH:",
  "library_name": "",
  "force_colors": "",
 }
]

COMPILATION_STATUS_COMPILING = 0
COMPILATION_STATUS_DONE = 1
COMPILATION_STATUS_FAILED = 2

RECURSION_LIMIT = 50


class COLS:
	FG_BLACK = "\033[30m"
	FG_RED = "\033[31m"
	FG_GREEN = "\033[32m"
	FG_YELLOW = "\033[33m"
	FG_BLUE = "\033[34m"
	FG_MAGENTA = "\033[35m"
	FG_CYAN = "\033[36m"
	FG_WHITE = "\033[37m"

	BG_BLACK = "\033[40m"
	BG_RED = "\033[41m"
	BG_GREEN = "\033[42m"
	BG_YELLOW = "\033[43m"
	BG_BLUE = "\033[44m"
	BG_MAGENTA = "\033[45m"
	BG_CYAN = "\033[46m"
	BG_WHITE = "\033[47m"

	FG_LIGHT_BLACK = "\033[90m"
	FG_LIGHT_RED = "\033[91m"
	FG_LIGHT_GREEN = "\033[92m"
	FG_LIGHT_YELLOW = "\033[93m"
	FG_LIGHT_BLUE = "\033[94m"
	FG_LIGHT_MAGENTA = "\033[95m"
	FG_LIGHT_CYAN = "\033[96m"
	FG_LIGHT_WHITE = "\033[97m"

	BG_LIGHT_BLACK = "\033[100m"
	BG_LIGHT_RED = "\033[101m"
	BG_LIGHT_GREEN = "\033[102m"
	BG_LIGHT_YELLOW = "\033[103m"
	BG_LIGHT_BLUE = "\033[104m"
	BG_LIGHT_MAGENTA = "\033[105m"
	BG_LIGHT_CYAN = "\033[106m"
	BG_LIGHT_WHITE = "\033[107m"

	RESET = "\033[0m"

	def erase_all():

		COLS.FG_BLACK = ""
		COLS.FG_RED = ""
		COLS.FG_GREEN = ""
		COLS.FG_YELLOW = ""
		COLS.FG_BLUE = ""
		COLS.FG_MAGENTA = ""
		COLS.FG_CYAN = ""
		COLS.FG_WHITE = ""

		COLS.BG_BLACK = ""
		COLS.BG_RED = ""
		COLS.BG_GREEN = ""
		COLS.BG_YELLOW = ""
		COLS.BG_BLUE = ""
		COLS.BG_MAGENTA = ""
		COLS.BG_CYAN = ""
		COLS.BG_WHITE = ""

		COLS.FG_LIGHT_BLACK = ""
		COLS.FG_LIGHT_RED = ""
		COLS.FG_LIGHT_GREEN = ""
		COLS.FG_LIGHT_YELLOW = ""
		COLS.FG_LIGHT_BLUE = ""
		COLS.FG_LIGHT_MAGENTA = ""
		COLS.FG_LIGHT_CYAN = ""
		COLS.FG_LIGHT_WHITE = ""

		COLS.BG_LIGHT_BLACK = ""
		COLS.BG_LIGHT_RED = ""
		COLS.BG_LIGHT_GREEN = ""
		COLS.BG_LIGHT_YELLOW = ""
		COLS.BG_LIGHT_BLUE = ""
		COLS.BG_LIGHT_MAGENTA = ""
		COLS.BG_LIGHT_CYAN = ""
		COLS.BG_LIGHT_WHITE = ""

		COLS.RESET = ""

		global PROGRESS_STATUS
		PROGRESS_STATUS = ["Processing", "Done", "Failed"]


PROGRRESS_PREFIXES: list[str] = ["|", "+", "-"]
PROGRESS_STATUS: list[str] = [f"{COLS.FG_BLUE}Processing", f"{COLS.FG_GREEN}Done", f"{COLS.FG_RED}Failed"]


def merge(a: dict, b: dict) -> dict:
	res: dict = {}

	res = copy.deepcopy(b)

	for key in a:
		if key in res:
			if isinstance(a[key], dict) and isinstance(res[key], dict):
				# both dict have the same key
				res[key] = merge(a[key], res[key])
		else:
			res[key] = copy.deepcopy(a[key])

	return res


def get_value(d: any, key: str, val="") -> dict | str:
	"""
	Tries to get the desired value from the dict, if fails returns val
	"""
	try:
		return d[key]
	except Exception:
		return val


def get_compilation_status(item: dict[str], tick: int = 0) -> str:

	# the first element is the spinner, takes up 1 char
	# the second is the name of the file being compiled, this should take at max 20 char
	# the last should be the textual status of compilation, it should start after the 20 chars of the name
	# / utils.cpp Compiling

	curr_spinner = SPINNERS[tick % len(SPINNERS)]

	print
	prefix: str = " " + PROGRRESS_PREFIXES[item["result"]] + " "
	suffix: str = " " + PROGRESS_STATUS[item["result"]]

	if item["result"] == 0:                 # Still compiling
		prefix = f" {curr_spinner} "
		suffix += "." * ((tick % 12) // 4 + 1) # makes the dots progress 1/4 the speed of the spinner

	# fill the string with spaces until 20 and truncate the string if longer than that
	name = item["name"].ljust(20)[:20]

	return prefix + COLS.FG_LIGHT_BLACK + name + suffix + COLS.RESET + "\n"


def print_progress(statuses: list[dict], settings: dict) -> None:
	"""
	Wait for the given process status be completed and prints its status in the meantime
	Returns when all the processes are done or failed
	"""

	GO_UP = "\x1b[1A"
	CLEAR_LINE = "\x1b[2K"

	# Animation state
	tick = 0
	while True:
		# How many lines to print at the same time
		num_lines = 0

		# Check if every process is done
		all_done = True
		for item in statuses:

			if settings["printing"]["skip_progress"] == "none":
				print(get_compilation_status(item, tick), end="")
				num_lines += 1
			elif settings["printing"]["skip_progress"] == "progress" and item["result"] == COMPILATION_STATUS_DONE:
				print(get_compilation_status(item, tick), end="")
				num_lines += 1
			if item["result"] == COMPILATION_STATUS_COMPILING:
				# If someone is still compiling keep looping
				all_done = False

		if all_done:
			break

		# Go up 1 line at the time and clear it
		for i in range(num_lines):
			print(GO_UP, end=CLEAR_LINE)

		# how quickly to refresh the printing
		time.sleep(0.15)
		tick += 1


def print_report(statuses: list[dict], settings: dict) -> None:
	"""
	Prints the report for every status there is in statuses
	"""

	if settings["printing"]["skip_reports"] == "all":
		return

	for item in statuses:

		if settings["printing"]["skip_reports"] == "empty":
			if item["output"] == "" and item["errors"] == "":
				# skip this report
				continue
		if settings["printing"]["skip_reports"] == "warn":
			if item["result"] != COMPILATION_STATUS_FAILED:
				# skip this report
				continue

		cmd = item["command"]
		name = item["name"].ljust(20)[:20]
		print(f" {name}{COLS.FG_LIGHT_BLACK} {cmd}{COLS.RESET}\n")

		# print stdout and stderr only if there is something to print

		if item["output"] != "":
			print(COLS.FG_LIGHT_BLUE, "    out", COLS.RESET, ":\n", item["output"], sep="")

		if item["errors"] != "":
			print(COLS.FG_LIGHT_RED, "    err", COLS.RESET, ":\n", item["errors"], sep="")


def compile_and_command(compilation_targets: list[str], settings: dict) -> None:
	"""
	calls compile()

	print compilation status

	calls link() if compilation was fine
	"""

	# --- Compiling ---

	print("\n", COLS.FG_GREEN, " --- Compiling ---", COLS.RESET)

	# where the status of the different compilations is stored
	compilations: list[dict] = []
	# compile each file and show the output,
	# and check for errors
	compile(compilation_targets, settings, compilations)

	print_progress(compilations, settings)
	print("")
	print_report(compilations, settings)

	compilation_failed: bool = False

	for item in compilations:
		if item["result"] == COMPILATION_STATUS_FAILED: # Failure
			compilation_failed = True

	# all compilations done, linking
	if compilation_failed:
		print(f"\n{COLS.FG_RED} --- Linking skipped due to errors in compilation process! ---")
		sys.exit(2)

	# cleaning prev compilation data
	compilations.clear()

	# --- Linking ---

	print("\n", COLS.FG_GREEN, " --- Linking ---", COLS.RESET)

	link_status = {
	 "result": COMPILATION_STATUS_COMPILING,
	 "name": "",
	 "output": "",
	 "errors": "",
	 "command": ""
	}

	# Link starts a thread, no need to check anything from him
	link(compilation_targets, settings, link_status)

	print_progress([link_status], settings)

	print("")

	# print
	print_report([link_status], settings)

	if link_status["result"] == COMPILATION_STATUS_FAILED:
		print(f"\n{COLS.FG_RED} --- Errors in linking process! ---")
		sys.exit(3)


def parse_profile_name(args: list[str]) -> str:
	try:
		return args[args.index("-p") + 1]
	except IndexError:
		# default profile
		return "default"


def parse_num_threads(args: list[str]) -> int:
	try:
		return int(args[args.index("-n") + 1])
	except ValueError:
		# default amount
		return 12
	except IndexError:
		# default amount
		return 12


def parse_file_path(filename: str) -> tuple[str, str, str] | None:
	# i need to differentiate different parts
	# extension: to decide if it has to be compiled or not and to name it
	# filename: everything else of the file name ignoring the extension, useful for naming compilitation files
	# source dir: necessary for differentiate eventual same-named files on different dirs

	# get file extension
	ext_pos = filename.rfind(".")
	filename_wo_extension = filename[:ext_pos]
	file_extension = filename[ext_pos + 1:]

	# get filename and relative source dir
	path: list[str] = filename_wo_extension.split("/")
	file_name: str = path[-1]
	full_directory: str = "/".join(path[:-1])

	return (full_directory, file_name, file_extension)


def cmd(command: str) -> [subprocess.Popen, str, str]:
	stream = subprocess.Popen(command.split(" "), stderr=subprocess.PIPE, stdout=subprocess.PIPE, universal_newlines=True)

	out, err = stream.communicate() # execute the command and get the result

	return stream, out, err


def exe_command(command: str, status: dict, sem: threading.Semaphore) -> int:
	"""
	execute the given command, set the ouput and return code to the correct structure
	"""

	sem.acquire()

	stream, out, err = cmd(command)

	ret = COMPILATION_STATUS_DONE
	if stream.returncode != 0: # the actual program return code, 0 is ok
		ret = COMPILATION_STATUS_FAILED

	status["output"] = out
	status["errors"] = err
	status["result"] = ret

	sem.release()

	return ret


def multi_thread(func: typing.Callable, ret: list, sem: threading.Semaphore, args: tuple):

	sem.acquire()

	ret[0] = func(*args)

	sem.release()

	ret[1] = True

	return ret


def get_includes(file: str) -> list[str]:
	"""
	Returns all of the includes included, directly or indirectly, bt the given file
	"""

	founds: list[str] = []
	# org_path: str = parse_file_path(file)[0]

	# TODO: Think about the MSVC children
	stream, out, err = cmd("cpp -MM " + file)

	# long live functional programming innit
	founds = list(filter(lambda x: x != "\\", out.split()[2:]))

	return founds


def parse_config_json(profile: str) -> dict[str, any]:
	"""
	Set the global variables by reading the from cpp_builder_config.json
	the optimization argument decide if debug or release mode
	"""

	settings: dict[str, any] = {
	                                          # type of compiler gcc like or rust like generally
	 "type": "gcc",

	                                          # name of the compiler and linker executable
	 "compiler": "gcc",
	 "linker": "gcc",

	                                          # compiler and linker args
	 "cargs": "",
	 "largs": "",

	                                          # output, includes, filenames swithces (/Fo -o) for msvc, clang, and gcc
	 "specifics": {},

	                                          # path and name of the final executable
	 "exe_path_name": "",

	                                          # base directory of the project
	 "project_path": "",

	                                          # the string composed by the path of the includes -> "-I./include -I./ext/include -I..."
	 "includes": "",

	                                          # list of all the includes as they appear in the config file
	 "raw_includes": [],

	                                          # directory where to leave the compiled object files
	 "objects_path": "",

	                                          # directories containing the names of the source directories
	 "source_files": [],

	                                          # the string composed by the names of the libraries -> "-lpthread -lm ..."
	 "libraries_names": "",

	                                          # the string composed by the path of the libraries -> "-L./path/to/lib -L..."
	 "libraries_paths": "",

	                                          # name of the scripts to execute
	 "scripts": {},

	                                          # semaphore to limit the number of concurrent threds that can be executed
	 "semaphore": threading.Semaphore(12),

	                                          # what to skip when printing
	 "printing": {
	  "skip_reports": "none",
	  "skip_progress": "none",
	  "colors": True
	 }
	}

	# load and parse the file
	config_filename = "cpp_builder_config.json"
	if os.path.isfile(config_filename):
		config_file = json.load(open(config_filename))
	else:
		print(COLS.FG_YELLOW, f"[WARNING]{COLS.FG_LIGHT_RED} Config file \"{config_filename}\" not found", COLS.RESET)
		return dict

	del config_filename

	# --- Compiler settings ---
	# get the compiler executable (gcc, g++, clang, rustc, etc)
	# and the linker executable, plus the type (needed for cli args)

	compiler_settings = get_value(config_file, "compiler")

	settings["compiler"] = get_value(compiler_settings, "compiler_exe", DEFAULT_COMPILER)

	settings["type"] = get_value(compiler_settings, "compiler_style", DEFAULT_COMPILER)

	# 0 gcc / clang
	# 1 msvc
	compiler_type: int = 0

	if settings["type"] == "gcc":
		compiler_type = 0
	elif settings["type"] == "clang":
		compiler_type = 0
	elif settings["type"] == "msvc":
		compiler_type = 1

	settings["specifics"] = COMPILER_SPECIFIC_ARGS[compiler_type]

	del compiler_type

	# if no linker is specified use the compiler executable
	settings["linker"] = get_value(compiler_settings, "linker_exe", settings["compiler"])

	del compiler_settings

	#
	# --- Directories settings ---
	#
	# Where is the project
	# where are the source files and the include files

	directories_settings = get_value(config_file, "directories")

	# base directory for ALL the other directories and files
	settings["project_path"] = get_value(directories_settings, "project_dir", "./")

	# name of the final executable
	settings["exe_path_name"] = get_value(directories_settings, "exe_path_name", "a.out")

	os.makedirs(os.path.dirname(settings["exe_path_name"]), exist_ok=True)

	targets: list[str] = []

	old_dir: str = os.getcwd()
	os.chdir(settings["project_path"])

	for sdir in get_value(directories_settings, "source_dirs", ["src"]):
		for path, subdirs, files in os.walk(sdir):
			for name in files:
				targets.append(f"{path}/{name}")

	os.chdir(old_dir)

	del old_dir, path, subdirs, files, name, sdir

	settings["source_files"] = targets

	del targets

	#
	# ---- Incudes ----
	#

	# create the includes args -> -IInclude -ISomelibrary/include -I...
	for Idir in get_value(directories_settings, "include_dirs", ["include"]):
		settings["raw_includes"].append(Idir)
		settings["includes"] += " " + settings["specifics"]["include_path"] + Idir

	settings["objects_path"] = get_value(directories_settings, "temp_dir", "obj")
	os.makedirs(settings["objects_path"], exist_ok=True) # create the obj directory

	del directories_settings

	#
	# ----- Profiles -----
	#

	default_settings = merge(EMPTY_PROFILE, get_value(config_file, "default", {}))

	profile_settings = merge(default_settings, get_value(config_file, profile, {}))

	# --- Scripts settings ---

	settings["scripts"] = get_value(profile_settings, "scripts", default_settings["scripts"])

	settings["profile"] = profile
	os.makedirs(settings["objects_path"] + "/" + settings["profile"], exist_ok=True) # create the profile directory

	#
	# --- Libs ---
	#

	# create the library args -> -lSomelib -lSomelib2 -l...
	for lname in get_value(profile_settings, "libraries_names", default_settings["libraries_names"]):
		settings["libraries_names"] += " " + settings["specifics"]["library_name"] + lname

	# cant be sure if it has been created
	# del lname

	# create the libraries path args -> -LSomelibrary/lib -L...
	for ldname in get_value(profile_settings, "libraries_dirs", default_settings["libraries_dirs"]):
		settings["libraries_paths"] += " " + settings["specifics"]["library_path"] + ldname

	# cant be sure if it has been created
	# del ldname

	#
	# --- Compiler and Linker arguments ---
	#

	settings["cargs"] = get_value(profile_settings, "compiler_args", default_settings["compiler_args"])
	settings["largs"] = get_value(profile_settings, "linker_args", default_settings["linker_args"])

	# fix for empty args
	if settings["cargs"]:
		settings["cargs"] = " " + settings["cargs"]

	if settings["largs"]:
		settings["largs"] = " " + settings["largs"]

	return settings


def to_recompile(filename: str, old_hashes: dict, new_hashes: dict) -> bool | str:
	"""
	Given a filename return if it needs to be recompiled
	A source file needs to be recompiled if it has been modified

	returns the filename is the file needs to be recompiled, false otherwise
	"""

	# get all the includes in one go, and remove any duplicate
	all_files: list[str] = list(dict.fromkeys(get_includes(filename)))
	all_files.insert(0, filename)

	res = False

	for curr in all_files:

		if curr in old_hashes:
			if old_hashes[curr] != new_hashes[curr]:
				res = filename
		else:
			new_hashes[curr] = make_new_file_hash(curr)
			res = filename

	return res


def make_new_file_hash(file: str) -> str:
	"""
	Calculate the hash for the given file an puts it in the new_hashes file
	"""
	# i need to re-instantiate the object to empty it
	sha1 = hashlib.sha1()

	try:
		# sha1 hash calculation
		with open(file, "rb") as f:
			sha1.update(f.read())
	except FileNotFoundError:
		pass

	return sha1.hexdigest() # create the new hash


def calculate_new_hashes(old_hashes: dict, new_hashes: dict) -> None:
	"""
	Calculate the hashes for all the source files
	"""

	for file in old_hashes: # loop trough every file of each directory

		new_hashes[file] = make_new_file_hash(file)


def load_old_hashes(directory: str) -> dict[str, str]:
	"""
	Load in old_hashes the hashes present in files_hash
	"""
	hashes: dict[str, str] = {}

	# creates the file
	if not os.path.exists(directory + HASH_FILENAME):
		return hashes
	# read hashes from files and add them to old_hashes array
	with open(directory + HASH_FILENAME, "r") as f:
		while True:
			data = f.readline()
			if not data:
				break
			temp = data.split(":")

			# remove trailing newline
			temp[1] = temp[1].replace("\n", "")
			hashes[temp[0]] = temp[1]

	return hashes


def save_new_hashes(new_hashes: dict[str, str], directory: str) -> None:
	"""
	Write all the hashes on files_hash
	"""

	with open(directory + HASH_FILENAME, "w") as f:
		for i in new_hashes.keys():
			f.write(i + ":")
			f.write(new_hashes[i] + "\n")


def get_to_compile(source_files: list[str], old_hashes: dict, new_hashes: dict, add_incl: list[str], sem: threading.Semaphore) -> list[str]:
	"""
	return a list of files and their directories that need to be compiled
	"""

	to_compile: list[tuple[str, str, str]] = [] # contains directory and filename

	# checking which file need to be compiled
	file: str = ""
	rets: list = []
	for file in source_files: # loop trough every file of each directory

		fname = parse_file_path(file)
		if fname[2] not in SOURCE_FILES_EXTENSIONS:
			continue

		rets.append([False, False])

		threading.Thread(target=multi_thread, args=(to_recompile, rets[-1], sem, (file, old_hashes, new_hashes))).start()

	exit = False
	while not exit:
		exit = True

		for i in rets:
			if i[1] is False:
				exit = False
				break

	for i in rets:
		if i[0] is not False:
			fname = parse_file_path(i[0])
			to_compile.append(fname)

	return to_compile


def compile(to_compile: list[str], settings: dict, compilations: list[dict]) -> None:
	"""
	Calls the compiler with the specified arguments
	"""

	cexe = settings["compiler"]
	includes = settings["includes"]
	cargs = settings["cargs"]
	obj_dir = settings["objects_path"] + "/" + settings["profile"]
	oargs = settings["specifics"]
	colors = oargs["force_colors"] if settings["printing"]["colors"] else oargs["no_colors"]

	for file in to_compile:
		obj_name: str = "".join(file[0].split("/"))

		command = f'{cexe} {colors}{cargs}{includes} {oargs["compile_only"]} {oargs["output_compiler"]}{obj_dir}/{obj_name}{file[1]}.{oargs["object_extension"]} {file[0]}/{file[1]}.{file[2]}'

		result = {
		 "result": COMPILATION_STATUS_COMPILING,
		 "name": f"{file[1]}.{file[2]}",
		 "output": "",
		 "errors": "",
		 "command": command
		}
		compilations.append(result)
		threading.Thread(target=exe_command, args=(command, result, settings["semaphore"])).start()


def link(to_compile: list[str], settings: dict, status: dict) -> None:
	"""
	Link together all the files that have been compiled with the specified libraries and arguments
	"""

	lexe = settings["linker"]
	largs = settings["largs"]
	epn = settings["exe_path_name"]
	libs = settings["libraries_paths"]
	obj_dir = settings["objects_path"] + "/" + settings["profile"]
	oargs = settings["specifics"]

	command = f'{lexe}{largs} {oargs["output_linker"]}{epn}{libs}'

	for path, subdirs, files in os.walk(obj_dir):
		for name in files:
			file = parse_file_path(name)
			if (file[2] != oargs["object_extension"]):
				continue
			obj_name: str = "".join(file[0].split("/"))

			command += f' {obj_dir}/{obj_name}{file[1]}.{oargs["object_extension"]}'

	command += settings["libraries_names"]

	status["name"] = epn
	status["command"] = command
	threading.Thread(target=exe_command, args=(command, status, settings["semaphore"])).start()


def exe_script(name: str, settings: dict):
	nm = settings["scripts"][name]
	result = {
	 "result": COMPILATION_STATUS_COMPILING,
	 "name": nm,
	 "output": "",
	 "errors": "",
	 "command": nm
	}
	threading.Thread(target=exe_command, args=(f'./{nm}', result, settings["semaphore"])).start()
	print_progress([result], settings)
	print("")
	print_report([result], settings)


def get_all_profiles():

	config_filename = "cpp_builder_config.json"
	if os.path.isfile(config_filename):
		config_file = json.load(open(config_filename))
	else:
		print(COLS.FG_YELLOW, f"[WARNING]{COLS.FG_LIGHT_RED} Config file \"{config_filename}\" not found", COLS.RESET)
		return dict

	profiles: list[str] = []

	for k in config_file:
		if k not in ["scripts", "compiler", "directories"]:
			profiles.append(k)

	return profiles


def create_makefile():

	profiles = get_all_profiles()

	if len(profiles) == 0:
		print(f"{COLS.FG_RED}At least one profile is needed in the config_file, but none found{COLS.RESET}")

	# first debug options
	settings = parse_config_json(profiles[0])

	# targets
	os.chdir(settings["project_path"])

	# obtain new hashes
	hashes: dict = {}

	calculate_new_hashes({}, hashes)

	# get the file needed to compile
	to_compile = get_to_compile(settings["source_files"], {}, hashes, settings["raw_includes"], settings["semaphore"])

	make_file = ""

	# variables

	make_file += f"CC       = {settings['compiler']}\n"
	make_file += f"BINNAME  = {settings['exe_path_name']}\n"
	make_file += f"OBJSDIR  = {settings['objects_path']}\n"
	make_file += f"INCLUDES = {settings['includes']}\n"
	make_file += "PROFILE  = \n"
	make_file += "CARGS    = \n"

	make_file += "\n"

	make_file += "OBJS = \\\n"
	for file in to_compile:
		obj_name: str = "".join(file[0].split("/")) + file[1]
		make_file += f"	$(OBJSDIR)/$(PROFILE)/{obj_name}.o \\\n"

	make_file += "\n"

	make_file += "SOURCES = \\\n"
	for file in to_compile:
		obj_name: str = "".join(file[0].split("/")) + file[1]
		make_file += f"	{file[0]}/{file[1]} \\\n"

	make_file += "\n\n"

	make_file += ".SUFFIXES:\n"

	make_file += "\n"

	make_file += "$(SOURCES):\n"
	make_file += "	$(CC) $@.cpp $(CARGS) $(INCLUDES) -c -o $(OBJSDIR)/$(PROFILE)/$(subst /,,$@).o\n"

	make_file += "\n\n"

	make_file += "# --- profiles ---\n"

	make_file += "\n\n"

	scripts_used: list[str] = []

	for prof in profiles:
		PROF = prof.upper()

		settings = parse_config_json(prof)

		# Profiles
		make_file += f"# --- {prof} ---\n"
		make_file += "\n"
		make_file += f"{PROF}-CARGS    = {settings['cargs']}\n"
		make_file += f"{PROF}-LARGS    = {settings['largs']}\n"
		make_file += f"{PROF}-LIBPATH  = {settings['libraries_paths']}\n"
		make_file += f"{PROF}-LIBNAMES = {settings['libraries_names']}\n"
		make_file += "\n\n"

		make_file += f"{prof}-link: PROFILE = {prof}\n"
		make_file += f"{prof}-link: CARGS = $({PROF}-CARGS)\n"
		make_file += f"{prof}-link: $(SOURCES)\n"
		make_file += f"	$(CC) $({PROF}-LARGS) -o $(BINNAME) $({PROF}-LIBPATH) $(OBJS) $({PROF}-LIBNAMES)\n"

		make_file += "\n"

		pre_rule = ""
		post_rule = ""

		if settings["scripts"]["pre"] != "":
			pre_rule = "{prof}-pre "
			scripts_used.append(pre_rule)
			make_file += f"{prof}-pre:\n"
			make_file += f"	./{settings['scripts']['pre']}\n"
			make_file += "\n"

		if settings["scripts"]["post"] != "":
			post_rule = f"{prof}-post"
			scripts_used.append(post_rule)
			make_file += f"{prof}-post:\n"
			make_file += f"	./{settings['scripts']['post']}\n"
			make_file += "\n"

		make_file += f"{prof}: | {pre_rule}{prof}-link {post_rule}\n"

		make_file += "\n"

	make_file += "\n"

	make_file += "# --- clean ---\n"
	make_file += "\n"

	make_file += "clean:\n"
	make_file += "	rm -r $(OBJSDIR)/*\n"
	make_file += "	rm -r $(BINNAME)\n"

	make_file += "\n\n"

	make_file += ".PHONY: clean "
	for i in scripts_used:
		make_file += i

	make_file += "\n"

	with open("Makefile", "w+") as mf:
		mf.write(make_file)


def main():

	args = sys.argv[1:]

	# makefile option
	if "-e" in args:
		create_makefile()
		exit(0)

	# generate an empty profile
	if "--gen" in args:
		with open("cpp_builder_config.json", "w") as f:
			f.write(TEMPLATE)
		exit(0)

	if "--help" in args or "-h" in args:
		print(HELP)
		exit(0)

	# profile selector
	if "-p" not in args:
		print(f"{COLS.FG_RED}You need to specify a profile with '-p'{COLS.RESET}")
		exit(1)

	compilation_profile = parse_profile_name(args)

	indx = args.index("-p")
	args.pop(indx + 1)
	args.pop(indx)

	# settings is garanteted to have all of the necessary values
	settings = parse_config_json(compilation_profile)

	compile_all = False

	for arg in args:

		if "-n" == arg:
			settings["semaphore"] = threading.Semaphore(parse_num_threads(sys.argv))
			continue
		# printing options

		if "--skip-empty-reports" == arg:
			settings["printing"]["skip_reports"] = "empty"
			continue

		if "--skip-warn-reports" == arg:
			settings["printing"]["skip_reports"] = "warn"
			continue

		if "--skip-all-reports" == arg:
			settings["printing"]["skip_reports"] = "all"
			continue

		if "--skip-progress" == arg:
			settings["printing"]["skip_progress"] = "progress"
			continue

		if "--skip-statuses" == arg:
			settings["printing"]["skip_progress"] = "statuses"
			continue

		if "--no-colors" == arg:
			COLS.erase_all()
			settings["printing"]["colors"] = False
			continue

		if "-a" == arg:
			compile_all = True
			continue

		# unknown switches, error
		print(f"{COLS.FG_RED}Unknown argument \"{arg}\" Exiting{COLS.RESET}")
		print(HELP)
		exit(1)

	# script are executed from the project path
	os.chdir(settings["project_path"])

	if settings["scripts"]["pre"] != "":
		print(COLS.FG_GREEN, " --- Pre Script ---", COLS.RESET)
		exe_script("pre", settings)

	hash_path = settings["objects_path"] + "/" + compilation_profile + "/"

	old_hashes: dict = {}

	# by not loading old hashes, all of the files results new
	if not compile_all:
		# load old hashes
		old_hashes = load_old_hashes(hash_path)

	new_hashes: dict = {}
	# obtain new hashes
	calculate_new_hashes(old_hashes, new_hashes)

	# get the file needed to compile
	to_compile = get_to_compile(settings["source_files"], old_hashes, new_hashes, settings["raw_includes"], settings["semaphore"])

	# if to_compile is empty, no need to do anything
	if not to_compile:
		print(f"{COLS.FG_YELLOW} --- Compilation and linking skipped due to no new or modified files ---{COLS.RESET}")
		return

	if not os.path.exists(settings["objects_path"]):
		os.makedirs(settings["objects_path"])

	compile_and_command(to_compile, settings)
	# manages compilation and printing

	if settings["scripts"]["post"] != "":
		print("\n", COLS.FG_GREEN, " --- Post Script ---", COLS.RESET)
		exe_script("post", settings)

	# do not overwrite the old hashes
	if not compile_all:
		save_new_hashes(new_hashes, hash_path)


if __name__ == "__main__":
	main()
