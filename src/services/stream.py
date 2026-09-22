

# The stream service is used to broadcast telemetry data from the primary replay process to any number of secondary processes/windows (e.g. for running data analysis or additional visualizations in parallel). It uses a simple TCP socket server to send telemetry frames as JSON-encoded messages. Secondary processes can connect to the stream server to receive real-time telemetry data for the current session.

import socket
import json
import threading
import time
from PySide6.QtCore import QThread, Signal

class TelemetryStreamServer:

  # This class is going to be hosted by the race_replay window process, which is the primary consumer of telemetry data. It will broadcast the telemetry frames

  def __init__(self, host='localhost', port=9999):
    self.host = host
    self.port = port
    self.clients = []
    self.clients_lock = threading.Lock()
    self.server_socket = None
    self.running = False

  def start(self):
    self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.server_socket.bind((self.host, self.port))
    self.server_socket.listen(5)
    self.running = True
    threading.Thread(target=self.accept_clients, daemon=True).start()
  
  def accept_clients(self):
    while self.running:
      try:
        client_socket, addr = self.server_socket.accept()
        print(f"Client connected from {addr}")
        with self.clients_lock:
          self.clients.append(client_socket)
        threading.Thread(target=self.handle_client, args=(client_socket,), daemon=True).start()
      except Exception as e:
        if self.running:
          print(f"Error accepting client: {e}")
        break

  def handle_client(self, client_socket):
    try:
      while self.running:
        time.sleep(1)  # Keep the connection alive
    except Exception as e:
      print(f"Client connection error: {e}")
    finally:
      client_socket.close()
      with self.clients_lock:
        try:
          self.clients.remove(client_socket)
        except ValueError:
          pass  # Already removed by broadcast() or stop()

  def broadcast(self, data):
    message = json.dumps(data).encode('utf-8')
    dead_clients = []
    
    with self.clients_lock:
      clients_copy = list(self.clients)
    
    for client in clients_copy:
      try:
        client.sendall(message + b'\n')
      except Exception as e:
        print(f"Error sending to client: {e}")
        client.close()
        dead_clients.append(client)
    
    if dead_clients:
      with self.clients_lock:
        for client in dead_clients:
          if client in self.clients:
            self.clients.remove(client)
  
  def stop(self):
    self.running = False
    if self.server_socket:
      self.server_socket.close()
    with self.clients_lock:
      for client in list(self.clients):
        client.close()
      self.clients = []

class TelemetryStreamClient(QThread):
    
  # This class is used by any secondary process/window that wants to consume the telemetry stream data. It connects to the stream server, receives data, and emits signals for the UI or other components to react to.

  data_received = Signal(dict)
  connection_status = Signal(str)
  error_occurred = Signal(str) 
  
  def __init__(self, host='localhost', port=9999):
    super().__init__()
    self.host = host
    self.port = port
    self.socket = None
    self.connected = False
    self.running = False
      
  def run(self):
    # Main thread loop - connects to server and receives data.
    self.running = True
    
    while self.running:
      try:
        self._connect_to_server()
        self._receive_data()
      except Exception as e:
        self.error_occurred.emit(f"Connection error: {str(e)}")
        if self.socket:
          self.socket.close()
        self.connected = False
        self.connection_status.emit("Disconnected")
        
        # Wait before attempting to reconnect
        self.sleep(2)
              
  def _connect_to_server(self):
    # Establish connection to the telemetry stream server.
    if self.connected:
      return
        
    self.connection_status.emit("Connecting...")
    self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.socket.settimeout(5.0)  # 5 second timeout
    
    try:
      self.socket.connect((self.host, self.port))
      self.connected = True
      self.connection_status.emit("Connected")
    except socket.timeout:
      self.error_occurred.emit(f"Connection timeout - is F1 Race Replay running?")
      raise
    except ConnectionRefusedError:
      self.error_occurred.emit(f"Connection refused - is F1 Race Replay running on {self.host}:{self.port}?")
      raise
          
  def _receive_data(self):
    # Receive and parse incoming telemetry data.
    buffer = ""
    
    while self.running and self.connected:
      try:
        # Receive data in chunks
        chunk = self.socket.recv(4096).decode('utf-8')
        if not chunk:
          # Server closed connection
          self.connected = False
          break
            
        buffer += chunk
        
        # Process complete messages (separated by newlines)
        while '\n' in buffer:
          line, buffer = buffer.split('\n', 1)
          if line.strip():
            try:
              data = json.loads(line.strip())
              self.data_received.emit(data)
            except json.JSONDecodeError as e:
              self.error_occurred.emit(f"JSON decode error: {str(e)}")
                      
      except socket.timeout:
        continue  # Keep trying
      except Exception as e:
        if self.running:  # Only report error if we're still supposed to be running
          self.error_occurred.emit(f"Receive error: {str(e)}")
        break
              
  def stop(self):
    # Stop the client thread.
    self.running = False
    self.connected = False
    if self.socket:
      self.socket.close()
