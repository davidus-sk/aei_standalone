#!/usr/bin/python3 -u

import serial
import serial.tools.list_ports
import time
from datetime import datetime
import re
import subprocess
import os

###############################################################################
## FUNCTIONS
###############################################################################

# Get the tty device number
def find_ttyusb_port_path():
	"""
	Uses serial.tools.list_ports.grep() to find a serial port whose 
	description contains the word "Converter" (case-insensitive) and 
	returns the ttyUSBx portion of the device name (e.g., ttyUSB0).

	Returns:
		str or None: The device file name (e.g., 'ttyUSB0', 'ttyACM1') 
					 if found, or None if no matching port is available.
	"""
	# Use grep to search for ports containing "converter" in their description,
	# hardware ID, or device path. The search is case-insensitive by default.
	# The result is a generator of ListPortInfo objects.
	ports = serial.tools.list_ports.grep("converter")

	# The grep function returns a generator, so we iterate through it.
	# We only care about the first match.
	try:
		# Get the first matching port information object
		port_info = next(ports)

		# The 'device' attribute holds the full device path (e.g., /dev/ttyUSB0)
		full_path = port_info.device

		# Use os.path.basename() to extract only the device file name
		# (e.g., 'ttyUSB0') from the full path.
		device_name = os.path.basename(full_path)

		print(f"\033[92mFound matching port: {port_info.description} at {full_path}\033[0m")
		return device_name

	except StopIteration:
		# StopIteration is raised if the generator is empty (no matching ports)
		print("\033[91mNo serial port containing 'Converter' was found.\033[0m")
		return None
	except Exception as e:
		print(f"\033[91mAn unexpected error occurred: {e}\033[0m")
		return None

# Loging fucntion
def logger(message):
	now = datetime.now()
	formatted = now.strftime("%Y-%m-%d %H:%M:%S")
	print(f"{formatted} > {message}")

# Sender function
def send_binary_to_serial(port, binary_data):
	if port.is_open:
		logger(f"\033[90mSending binary data: {binary_data.hex()} ({len(binary_data)} bytes)\033[0m")

		try:
			bytes_written = port.write(binary_data)
			logger(f"\033[90mSuccessfully wrote {bytes_written} bytes.\033[0m")
			time.sleep(0.1)
		except serial.SerialException as write_error:
			logger(f"\033[91mError during write/read: {write_error}\033[0m")
		except Exception as e:
			logger(f"\033[91mAn unexpected error occurred during write/read: {e}\033[0m")

def get_reader_status(port):
	logger(f"\033[92mGetting reader status.\033[0m")
	send_binary_to_serial(port=port, binary_data=b'\xFA\x00\x06\x7A\xF5')
	received_data = port.read_all()
	logger(f"\033[90mReceived data: {received_data.hex()} ({len(received_data)} bytes)\033[0m")

	if len(received_data) > 0:

		b1 = received_data[4]
		b2 = received_data[6]

		status = (b1 >> 6) & 1
		frequency = b1 & 3
		power = b2

		logger(f"\033[96mRF = {status}, Frequency = {frequency}, Power = {power}%\033[0m")
	else:
		logger(f"\033[91mNo data was received.\033[0m")

def process_bytes(input_bytes: bytes) -> bytes:
	"""
	Processes a bytes object, unpacking 6-bit chunks into 8-bit bytes.
	"""
	output = []
	bit_buffer = 0      # Will hold bits temporarily
	bits_in_buffer = 0  # Number of bits currently in buffer

	# Iterating over a 'bytes' object gives you integers
	for byte in input_bytes:
		# Keep only the lower 6 bits
		byte &= 0x3F

		# Shift the buffer left 6 bits and OR the new 6 bits in
		bit_buffer = (bit_buffer << 6) | byte
		bits_in_buffer += 6

		# While we have enough bits for a full byte
		while bits_in_buffer >= 8:
			# Extract the top 8 bits
			bits_in_buffer -= 8
			output_byte = (bit_buffer >> bits_in_buffer) & 0xFF
			output.append(output_byte)

	# We ignore any leftover bits < 8 at the end

	# Convert the list of integers back into a bytes object
	return bytes(output)

def unpack_6bit_to_8bit(input_bytes: bytes) -> bytes:
	"""
	Unpacks a byte string where each byte represents 6 bits of data.

	The input format is assumed to be 2 padding bits followed by 6 data bits
	(e.g., '00XXXXXX'). This function extracts the 6 'X' bits from each
	byte, concatenates them into a continuous bitstream, and then re-parses
	that stream into full 8-bit bytes.

	Any leftover bits at the end that do not form a full 8-bit byte
	are discarded.

	Args:
		input_bytes: A 'bytes' object containing the 6-bit-per-byte data.

	Returns:
		A 'bytes' object with the data repacked into 8-bit bytes.
	"""
	bit_buffer = 0       # An integer to act as a bit-stream buffer
	buffer_length = 0    # How many bits are currently in the buffer
	output_bytes = bytearray()  # A mutable list of bytes for our output

	#
	# This visualization shows how bits are masked and combined.
	# We mask with 0x3F (0b00111111) to get the 6 data bits, then
	# shift the buffer left by 6 to make room for the new bits.

	for byte in input_bytes:
		# 1. Get the 6 significant bits by masking with 0x3F (0b00111111).
		# This effectively removes the '00' padding on the left.
		# Example: 0b00110101 & 0b00111111 = 0b00110101 (which is 110101)
		six_bits = byte & 0x3F

		# 2. Add these 6 bits to our buffer.
		# We shift the existing buffer left by 6 to make room,
		# then 'or' the new 6 bits in.
		bit_buffer = (bit_buffer << 6) | six_bits
		buffer_length += 6  # We've added 6 bits

		# 3. While the buffer has enough bits to make one or more
		#    full 8-bit bytes, extract them.
		while buffer_length >= 8:
			# We need to extract the *top* 8 bits from the buffer.
			# To do this, we shift the buffer right so the 8 bits
			# we want are at the far right.
			shift_amount = buffer_length - 8
			new_byte = (bit_buffer >> shift_amount) & 0xFF  # 0xFF is a mask for 8 bits

			# 4. Add the new 8-bit byte to our output
			output_bytes.append(new_byte)

			# 5. Remove the 8 bits we just extracted from the buffer.
			# We create a 'mask' for the bits we want to *keep*.
			# (1 << shift_amount) - 1 creates a mask of 'shift_amount' ones.
			# Example: if shift_amount is 4, (1 << 4) = 16, 16-1 = 15 = 0b1111
			mask = (1 << shift_amount) - 1
			bit_buffer = bit_buffer & mask  # Keep only the leftover bits

			# 6. Update the buffer length
			buffer_length -= 8

	# The loop is done. Any remaining bits in bit_buffer (if buffer_length < 8)
	# are discarded as they don't form a full byte.

	return bytes(output_bytes)


def bits_to_int(bit_array, start_bit, end_bit):
	"""
	Converts a slice of a boolean array (bits) into an integer.
	The bits are read from left to right (MSB to LSB).
	Indices are 0-based. start_bit is inclusive, end_bit is exclusive.
	"""
	if start_bit >= end_bit or end_bit > len(bit_array):
		return 0

	number = 0
	slice_len = end_bit - start_bit
	for i in range(slice_len):
		# The bit to check is at index start_bit + i
		if bit_array[start_bit + i]:
			# Add the corresponding power of 2
			# (slice_len - 1 - i) calculates the bit's positional value
			power = (slice_len - 1 - i)
			number += (1 << power) # 1 << power is equivalent to 2**power

	return number

def car_number(input_bytes: bytes):
	# --- 1. Convert byte string to a single array of bits ---
	# We create a list of booleans, where True=1 and False=0.
	bit_array = []
	for byte in input_bytes:
		# Iterate from the most significant bit (MSB) to the LSB
		for i in range(7, -1, -1):
			bit = (byte >> i) & 1
			bit_array.append(bit == 1)

	# --- 2. Define the extraction range (0-based) ---
	# You want bits "26 through 45" inclusive, assuming the string starts at bit 0.
	start_index = 26
	end_index = 45 # inclusive

	# The bits_to_int function uses an exclusive end bit, so we add 1.
	call_start_bit = start_index
	call_end_bit = end_index + 1
	num_bits = call_end_bit - call_start_bit

	# --- 3. Extract the bits ---
	extracted_value = bits_to_int(bit_array, call_start_bit, call_end_bit)

	return extracted_value

def decode_c1(n1):
	"""
	Decodes the first character (N1) of the Equipment Initial.
	A=0, B=1, ... Z=25
	"""
	if 0 <= n1 <= 25:
		return chr(n1 + 65) # 0 -> 'A' (65)
	return '?'

def decode_c2_c4(n):
	"""
	Decodes characters 2, 3, or 4 (N2, N3, N4) of the Equipment Initial.
	Blank=0, A=1, B=2, ... Z=26
	"""
	if n == 0:
		return ' ' # Blank
	if 1 <= n <= 26:
		return chr(n + 64) # 1 -> 'A' (65)
	return '?'

def car_owner(input_bytes: bytes):
	# --- 1. Convert byte string to a single array of bits ---
	# We create a list of booleans, where True=1 and False=0.
	bit_array = []
	for byte in input_bytes:
		# Iterate from the most significant bit (MSB) to the LSB
		for i in range(7, -1, -1):
			bit = (byte >> i) & 1
			bit_array.append(bit == 1)

	# --- 2. Define the extraction range (0-based) ---
	# You want bits "7 through 25" inclusive, assuming the string starts at bit 0.
	start_index = 7
	end_index = 25 # inclusive

	# The bits_to_int function uses an exclusive end bit, so we add 1.
	call_start_bit = start_index
	call_end_bit = end_index + 1
	num_bits = call_end_bit - call_start_bit

	# --- 3. Extract the bits as a single decimal "Value" ---
	# This is the "Value" from your decoding formula
	value = bits_to_int(bit_array, call_start_bit, call_end_bit)

	# --- 5. Decode "Value" using the mixed-base-27 formula ---

	# Define the powers of 27
	POW_27_3 = 27**3  # 19683
	POW_27_2 = 27**2  # 729
	POW_27_1 = 27

	# 1. N1 = Value/27^3 (integer—drop fractions)
	n1 = value // POW_27_3

	# 2. N2 = (Value – (N1 × 27^3))/27^2 (integer)
	remainder_n1 = value - (n1 * POW_27_3)
	n2 = remainder_n1 // POW_27_2

	# 3. N3 = (Value – ((N1 × 27^3) + (N2 × 27^2)))/27 (integer)
	remainder_n2 = remainder_n1 - (n2 * POW_27_2)
	n3 = remainder_n2 // POW_27_1

	# 4. N4 = Value – ((N1 × 27^3) + (N2 × 27^2) + (N3 × 27))
	remainder_n3 = remainder_n2 - (n3 * POW_27_1)
	n4 = remainder_n3

	# 5. Use the letter-to-number assignments to convert
	c1 = decode_c1(n1)
	c2 = decode_c2_c4(n2)
	c3 = decode_c2_c4(n3)
	c4 = decode_c2_c4(n4)

	return f"{c1}{c2}{c3}{c4}"


###############################################################################
## MAIN
###############################################################################

# Get TTY
tty = find_ttyusb_port_path()

if not tty:
	logger(f"\033[91mNo USB tty found. Exiting...\033[0m")
	exit()

# Connect to serial port
try:
	port = serial.Serial(
		port=f"/dev/{tty}",
		baudrate=57600,
		parity=serial.PARITY_NONE,
		stopbits=serial.STOPBITS_ONE,
		bytesize=serial.EIGHTBITS,
		timeout=10
	)

except serial.SerialException as connect_error:
	logger(f"\033[91mError: Could not open serial port '{port}'.\033[0m")
	logger(f"\033[91mDetails: {connect_error}\033[0m")
except Exception as e:
	logger(f"\033[91mAn unexpected error occurred: {e}\033[0m")

if not port:
	logger(f"\033[91mSerial port connection failed. Exiting...\033[0m")
	exit()

#
# Send commands to the reader
#

# Turn RF off
logger(f"\033[92mTurning RF off.\033[0m")
send_binary_to_serial(port=port, binary_data=b'\xFA\x00\x05\x7B\xF5')
received_data = port.read_all()
logger(f"\033[90mReceived data: {received_data.hex()} ({len(received_data)} bytes)\033[0m")

# Tell reader to use serial
logger(f"\033[92mSetting reader for serial coms.\033[0m")
send_binary_to_serial(port=port, binary_data=b'\xFA\x00\x43\x5A\x01\x62\xF5')
received_data = port.read_all()
logger(f"\033[90mReceived data: {received_data.hex()} ({len(received_data)} bytes)\033[0m")

# Set RF to 100%
logger(f"\033[92mSetting RF to 100%.\033[0m")
send_binary_to_serial(port=port, binary_data=b'\xFA\x00\x0C\x64\x10\xF5')
received_data = port.read_all()
logger(f"\033[90mReceived data: {received_data.hex()} ({len(received_data)} bytes)\033[0m")

# Turn RF on
logger(f"\033[92mTurning RF on.\033[0m")
send_binary_to_serial(port=port, binary_data=b'\xFA\x00\x0A\x76\xF5')
received_data = port.read_all()
logger(f"\033[90mReceived data: {received_data.hex()} ({len(received_data)} bytes)\033[0m")

# Globals
last_tag = ''
last_read = time.time()

# Start reading
logger(f"\033[93mEntering read loop.\033[0m")
while True:
	received_data = port.readline()

	if len(received_data) > 0:
		last_read = time.time()
		logger(f"\033[90mRaw read: {received_data.hex()}\033[0m")

		# Extract the needed bytes
		pattern = re.compile(b'\xfa\x00\x07(.*?)\xf5', re.DOTALL)
		matches = pattern.findall(received_data)

		for i, raw_packet in enumerate(matches):
			logger(f"\033[90mFound pattern: {raw_packet.hex()}\033[0m")

			unpacked = unpack_6bit_to_8bit(raw_packet)
			owner = car_owner(unpacked)
			number = car_number(unpacked)
			current_tag = f"{owner} {number}"

			logger(f"\033[90mFound tag: {current_tag}\033[0m")

			with open("/tmp/tags.log", 'a') as file:
				file.write(f"{last_read},{current_tag}\n")

			if last_tag != current_tag:
				last_tag = current_tag
				logger(f"\033[92mStoring tag for sending to the recipients\033[0m")

				with open(f"/dev/shm/{last_read}-{i}.tag", 'w') as file:
					file.write(f"{current_tag}\n")

		# Got a read, no need for status check
		continue

	# No reads received, let's get reader's status
	time.sleep(0.1)
	get_reader_status(port)
