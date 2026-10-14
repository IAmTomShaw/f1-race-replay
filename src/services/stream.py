# The stream service is used to broadcast telemetry data from the primary replay process to any number of secondary processes/windows (e.g. for running data analysis or additional visualizations in parallel). It uses a simple TCP socket server to send telemetry frames as JSON-encoded messages. Secondary processes can connect to the stream server to receive real-time telemetry data for the current session.

import socket
import json
import threading
import time
from PySide6.QtCore import QThread, Signal
from src.streaming.protocol import PROTOCOL_VERSION


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
    self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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
    self._stop_requested = False
      
  def run(self):
    # Main thread loop - connects to server and receives data.
    if self._stop_requested:
      return
    self.running = True
    
    while self.running:
      try:
        self._connect_to_server()
        self._receive_data()
      except Exception as e:
        if not self.running:
          break
        self.error_occurred.emit(f"Connection error: {str(e)}")
        if self.socket:
          self.socket.close()
        self.connected = False
        self.connection_status.emit("Disconnected")
        
        if self.running:
          self.sleep(2)
              
  def _connect_to_server(self):
    # Establish connection to the telemetry stream server.
    if self.connected:
      return
        
    self.connection_status.emit("Connecting...")
    self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.socket.settimeout(1.0)
    
    try:
      self.socket.connect((self.host, self.port))
      self.connected = True
      self.connection_status.emit("Connected")
    except socket.timeout:
      self.error_occurred.emit("Connection timeout - is F1 Race Replay running?")
      raise
    except ConnectionRefusedError:
      self.error_occurred.emit(f"Connection refused - is F1 Race Replay running on {self.host}:{self.port}?")
      raise
          
  def _receive_data(self):
    # Receive and parse incoming telemetry data using byte buffering so
    # multi-byte UTF-8 characters split across recv() chunks never fail.
    buffer = b""
    
    while self.running and self.connected:
      try:
        raw_chunk = self.socket.recv(4096)
        if not raw_chunk:
          # Server closed connection
          self.connected = False
          break
        if isinstance(raw_chunk, str):
          raw_chunk = raw_chunk.encode("utf-8")
        buffer += raw_chunk
        
        # Process complete messages (separated by newlines)
        while b'\n' in buffer:
          line_bytes, buffer = buffer.split(b'\n', 1)
          line = line_bytes.decode('utf-8', errors='replace').strip()
          if line:
            try:
              data = json.loads(line)
              if isinstance(data, dict):
                if "raw" in data and "envelope" in data:
                  self.data_received.emit(data["raw"])
                elif "payload" in data and "type" in data and "version" in data:
                  self.data_received.emit(data["payload"])
                else:
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
    self._stop_requested = True
    self.running = False
    self.connected = False
    if self.socket:
      try:
        self.socket.shutdown(socket.SHUT_RDWR)
      except OSError:
        pass
      finally:
        self.socket.close()
        self.socket = None


# ---------------------------------------------------------------------------
# TASK 3: the V2 client decodes the protocol envelope and emits
# the raw payload together with envelope metadata.
# ---------------------------------------------------------------------------
class TelemetryStreamClientV2(QThread):
  """Consumer that decodes the protocol envelope."""

  envelope_received = Signal(dict)
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
    self._stop_requested = False

  def run(self):
    if self._stop_requested:
      return
    self.running = True
    while self.running:
      try:
        self._connect_to_server()
        self._receive_data()
      except Exception as e:
        if not self.running:
          break
        self.error_occurred.emit(f"Connection error: {str(e)}")
        if self.socket:
          try:
            self.socket.close()
          except OSError:
            pass
        self.connected = False
        self.connection_status.emit("Disconnected")
        if self.running:
          self.sleep(2)

  def _connect_to_server(self):
    if self.connected:
      return
    self.connection_status.emit("Connecting...")
    self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.socket.settimeout(1.0)
    try:
      self.socket.connect((self.host, self.port))
      self.connected = True
      self.connection_status.emit("Connected")
    except socket.timeout:
      self.error_occurred.emit("Connection timeout")
      raise
    except ConnectionRefusedError:
      self.error_occurred.emit("Connection refused")
      raise

  def _receive_data(self):
    buffer = b""
    while self.running and self.connected:
      try:
        raw_chunk = self.socket.recv(4096)
        if not raw_chunk:
          self.connected = False
          break
        if isinstance(raw_chunk, str):
          raw_chunk = raw_chunk.encode("utf-8")
        buffer += raw_chunk
        while b'\n' in buffer:
          line_bytes, buffer = buffer.split(b'\n', 1)
          line = line_bytes.decode('utf-8', errors='replace').strip()
          if line:
            try:
              envelope = json.loads(line)
            except json.JSONDecodeError as e:
              self.error_occurred.emit(f"JSON decode error: {str(e)}")
              continue
            if isinstance(envelope, dict):
              if "payload" in envelope and "type" in envelope and "version" in envelope:
                if envelope.get("version") != PROTOCOL_VERSION:
                  self.error_occurred.emit(
                      f"Protocol version mismatch: {envelope.get('version')} != {PROTOCOL_VERSION}"
                  )
                  continue
                # Direct protocol envelope (src.streaming.transport wire format)
                self.envelope_received.emit(envelope)
                payload = envelope.get("payload", {})
                self.data_received.emit(payload if isinstance(payload, dict) else {"payload": payload})
              elif "envelope" in envelope:
                # Transitional {"envelope": ..., "raw": ...}
                env = envelope.get("envelope", {})
                raw = envelope.get("raw", {})
                self.envelope_received.emit(env if isinstance(env, dict) else {})
                self.data_received.emit(raw if isinstance(raw, dict) else {})
              else:
                # Bare legacy payload
                self.envelope_received.emit({})
                self.data_received.emit(envelope)
      except socket.timeout:
        continue
      except Exception as e:
        if self.running:
          self.error_occurred.emit(f"Receive error: {str(e)}")
        break

  def stop(self):
    self._stop_requested = True
    self.running = False
    self.connected = False
    if self.socket:
      try:
        self.socket.shutdown(socket.SHUT_RDWR)
      except OSError:
        pass
      finally:
        self.socket.close()
        self.socket = None
