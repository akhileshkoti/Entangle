import socket
import struct

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(('127.0.0.1', 5555))

print("Connected! Receiving frames...")

with open('output.h264', 'wb') as f:
    count = 0
    while count < 100:  # Receive first 100 frames
        try:
            header = sock.recv(13)
            if not header:
                break

            codec_id = header[0]
            pts = struct.unpack('>Q', header[1:9])[0]
            size = struct.unpack('>I', header[9:13])[0]

            frame_data = sock.recv(size)
            f.write(frame_data)

            count += 1
            if count % 10 == 0:
                print(f"Received {count} frames")
        except Exception as e:
            print(f"Error: {e}")
            break

sock.close()
print("Done! Play with: ffplay output.h264")