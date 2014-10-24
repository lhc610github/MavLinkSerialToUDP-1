import multiprocessing
import time
import socket
import serial
import logging
import sys
import os
import time
import signal

def open_port(portname, baudrate):
  try:
    return serial.Serial(portname, baudrate)
  except serial.SerialException as e:
    logging.debug("Could not open serial port: {}".format(portname, e))
    print ("Could not open serial port: {}".format(portname, e))
  return None

def serial_to_udp(connected, lock, py_serial, udp_socket, udp_client):
    connected.wait()
    while py_serial.isOpen():
        msg = bytearray()
        msg.append(0)
        payload_length = bytearray()
        payload_length.append(0)
        try:
            lock.acquire()
            msg[0] = py_serial.read(1)
            if msg[0] == 254:
                #payload_length[0] = py_serial.read()
                #msg.append(payload_length[0])
                #payload = py_serial.read(payload_length[0] + 6)
                msg.append(py_serial.read())
                msg += py_serial.read(msg[1] + 6)
                #for x in payload:
                #    msg.append(x)
        except serial.SerialTimeoutException as e:
            logging.error("Read timeout on serial port")
        except serial.SerialException as e:
            logging.error("Read exception on serial port")
        else:
            bytes = udp_socket.sendto(msg, udp_client)
        finally:
            lock.release()

def udp_to_serial(connected, lock, py_serial, udp_socket):
    connected.wait()
    while py_serial.isOpen():
        time.sleep(0.005)
        try:
            udp_data, udp_client = udp_socket.recvfrom(512)            	# receive data on UDP
        except socket.timeout:
            logging.error("Read timeout on socket")
        except:
            pass
        else:
            try:
                lock.acquire()
                bytes = py_serial.write(udp_data)
            except serial.SerialTimeoutException as e:
                print "Write timeout on serial port"
            except serial.SerialException as e:
                print "Write exception serial port"
            finally:
                py_serial.flushInput()
                lock.release()

def exit_gracefully(signal, frame):
    py_serial.close()
    sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, exit_gracefully)
    if ( len(sys.argv) == 1 ):
        print "MavLink UDP Proxy by Nils Hogberg, 2014"
        print "Syntax: " + sys.argv[0] + " serial_port baud_rate(=57600) udp_ip(= 127.0.0.1) udp_port(= 14550)"
        print "Example: " + sys.argv[0] + " /dev/ttyAMA0 57600 127.0.0.1 14550"
        quit()

    serial_port = sys.argv[1]

    if ( len(sys.argv) >= 3 ):
        baud_rate = sys.argv[2]
    else:
        baud_rate = "57600"
    if ( len(sys.argv) >= 4 ):
        udp_ip = sys.argv[3]
    else:
        udp_ip = "127.0.0.1"
    if ( len(sys.argv) >= 5 ):
        udp_port = sys.argv[4]
    else:
        udp_port = "14550"
        
    print "Reading from serial port: " + serial_port + ":" + baud_rate
    print "Sending to " + udp_ip + ":" + udp_port	

    lock = multiprocessing.Lock()
    # set when connection is established with GCS
    connected = multiprocessing.Event()
    
    # UDP Socket
    udp_port = int(udp_port)
    udp_client = (udp_ip, udp_port)
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind(('0.0.0.0', udp_port))
    udp_socket.setblocking(0)
    baud_rate = int(baud_rate)
    py_serial    = None

    py_serial = open_port(serial_port, baud_rate)
    if py_serial is None:
            print "Could not open serial port. Script exit."
            sys.exit(1)
            
    sertoudp = multiprocessing.Process(name='sertoudp', target=serial_to_udp, args=(connected, lock, py_serial, udp_socket, udp_client))
    udptoser = multiprocessing.Process(name='udptoser', target=udp_to_serial, args=(connected, lock, py_serial, udp_socket))
    
    print "starting processes"
    sertoudp.start()
    udptoser.start()

    client_cnct = False
    while client_cnct is False:
        time.sleep(1)
        bytes = udp_socket.sendto('hello', udp_client)
        try:
	    udp_data, udp_client = udp_socket.recvfrom(512)
            if udp_data is not None:
                client_cnct = True
                print "GCS connection from: ", udp_client
        except:
            pass
        else:
            try:
                bytes = py_serial.write(udp_data)
            except serial.SerialTimeoutException as e:
                print "Write timeout on serial port"
            except serial.SerialException as e:
                print "Write exception serial port"
            finally:
                py_serial.flushInput()

    print "setting event"
    connected.set()

    print "wait for processes to finish"
    sertoudp.join()
    udptoser.join()
    
