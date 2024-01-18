import os
import socket
import struct
import threading
import time
import urllib.parse

# Reading environment variables
LMS_SERVER_IP = os.environ['LMS_SERVER_IP']
LMS_SERVER_PORT = int(os.environ['LMS_SERVER_PORT'])
LMS_USERNAME = os.environ['LMS_USERNAME']
LMS_PASSWORD = os.environ['LMS_PASSWORD']
PLAYER_MAC = os.environ['PLAYER_MAC']
TARGET_FPS = int(os.environ['TARGET_FPS'])
RETRY_DELAY_SEC = int(os.environ['RETRY_DELAY_SEC'])
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
ARTNET_TARGET_IP = os.environ['ARTNET_TARGET_IP']
ARTNET_TARGET_PORT = int(os.environ['ARTNET_TARGET_PORT'])

frame_count = 0

def debug_print(message):
    if DEBUG:
        print(message, flush=True)

def connect_to_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((LMS_SERVER_IP, LMS_SERVER_PORT))
    return s

def construct_artnet_timecode_packet(hours, minutes, seconds, frames):
    packet_id = "Art-Net\0"
    op_code = 0x9700  # OpCode for ArtTimeCode packet
    prot_ver_hi = 0
    prot_ver_lo = 14  # Protocol version 14
    type_smpte = 3  # Type for SMPTE (30fps)

    # Convert OpCode to little-endian format
    op_code_le = op_code.to_bytes(2, byteorder='little')

    # Packet format: ID (8 bytes), OpCode (2 bytes, little-endian), Protocol version (2 bytes), Timecode (4 bytes), Type (1 byte)
    packet_format = "!8s2sBBxx4BB"
    artnet_packet = struct.pack(packet_format, packet_id.encode('utf-8'), op_code_le, prot_ver_hi, prot_ver_lo, frames, seconds, minutes, hours, type_smpte)

    return artnet_packet

def send_udp_packet(packet, target_ip, target_port):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(packet, (target_ip, target_port))

def fps_counter():
    global frame_count
    while True:
        time.sleep(1)
        print(f"FPS: {frame_count}", flush=True)
        frame_count = 0

def main():
    global frame_count

    # Desired FPS
    target_interval = 1.0 / TARGET_FPS

    fps_thread = threading.Thread(target=fps_counter)
    fps_thread.daemon = True
    fps_thread.start()

    last_sent_time = float(-1)

    while True:
        try:
            with connect_to_server() as s:
                login_command = f"login {LMS_USERNAME} {LMS_PASSWORD}\n"
                s.sendall(login_command.encode())
                _ = s.recv(1024)

                while True:
                    start_time = time.time()

                    escaped_mac = urllib.parse.quote(PLAYER_MAC)

                    # Send mode query and check response
                    mode_query = f"{escaped_mac} mode ?\n"
                    s.sendall(mode_query.encode())
                    mode_response = s.recv(1024).decode().split(' ')[-1].strip()
                    if mode_response != "play":
                        time.sleep(10/1000)
                        continue  # Skip this iteration if mode is not "play"

                    # Send time query
                    time_query = f"{escaped_mac} time ?\n"
                    s.sendall(time_query.encode())
                    response = s.recv(1024).decode()
                    current_time_str = response.split(' ')[-1].strip()
                    current_time = float(current_time_str)

                    if last_sent_time is None or current_time != last_sent_time:
                        hours = int(current_time // 3600)
                        minutes = int((current_time % 3600) // 60)
                        seconds = int(current_time % 60)
                        frames = int((current_time % 1) * 30)

                        artnet_packet = construct_artnet_timecode_packet(hours, minutes, seconds, frames)
                        send_udp_packet(artnet_packet, ARTNET_TARGET_IP, ARTNET_TARGET_PORT)

                        last_sent_time = current_time
                        frame_count += 1

                    end_time = time.time()
                    processing_time = end_time - start_time
                    sleep_time = max(target_interval - processing_time, 0)
                    time.sleep(sleep_time)

        except Exception as e:
            print(f"An error occurred: {e}. Retrying in {RETRY_DELAY_SEC} seconds.", flush=True)
            time.sleep(RETRY_DELAY_SEC)

if __name__ == "__main__":
    main()

