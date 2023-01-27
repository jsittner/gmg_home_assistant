"""Green Mountain Grill API library"""


#from audioop import add
#from distutils.log import error
#from email import message
import socket
import binascii
import ipaddress
import time
import logging

_LOGGER = logging.getLogger(__name__)


def grills(timeout = 1, ip_bind_address = '0.0.0.0'):

    _LOGGER.debug("Opening up udp sockets and broadcasting for grills.")
   
    interfaces = socket.getaddrinfo(host=socket.gethostname(), port=None, family=socket.AF_INET)
    allips = [ip[-1][0] for ip in interfaces]
    allips.append(ip_bind_address)

    grills = [] 
    message = grill.CODE_SERIAL

    
    for ip in allips:
        _LOGGER.debug(f"Creating socket for IP: {ip}")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            #Bind to the specific IP for the adapter and use port 0 to signify any open port by the OS
            sock.bind((ip, 0))
            
            # Each recv should have the full timeout period to complete
            sock.settimeout(timeout)

            sock.sendto(message, ('<broadcast>', grill.UDP_PORT))

            _LOGGER.debug("Broadcast sent.")

            while True:
                addGrill = True
                # Get some packets from the network
                data, (address, retSocket) = sock.recvfrom(1024)
                response = data.decode('utf-8')

                _LOGGER.debug(f"Received a response {address}:{retSocket}, {response}")
                # Confirm it's a GMG serial number
                try:
                    if response.startswith('GMG'):
                        _LOGGER.debug(f"Found grill {address}:{retSocket}, {response}")
                        for grillTest in grills:
                            if grillTest._serial_number == response:  # TODO: Define a property for serial number
                                _LOGGER.debug(f"Grill {response} is a duplicate.  Not adding to collection.")
                                addGrill = False

                        if addGrill:
                            grills.append(grill(address, response))
                except ValueError:
                    pass

        except socket.timeout:
            # This will always happen, a timeout occurs when we no longer hear from any grills
            # This is the required flow to break out of the `while True:` statement above.
            _LOGGER.debug("Socket timed out.")
        finally:
            # Always close the socket
            sock.close()

    _LOGGER.debug(f"Found {len(grills)} grills.")
    return grills


class grill(object):
    UDP_PORT = 8080
    MIN_TEMP_F = 150 # Minimum temperature in degrees Fahrenheit
    MAX_TEMP_F = 500 # Maximum Temperature in degrees Fahrenheit
    MIN_TEMP_F_PROBE = 32 # Mimimum temperature in degrees Fahrenheit
    MAX_TEMP_F_PROBE = 257 # Maximum temperature in degrees Fahrenheit 
    
    CODE_SERIAL = b'UL!'
    CODE_STATUS = b'UR001!'
    
    def __init__(self, ip, serial_number = ''):
        
        if not ipaddress.ip_address(ip):
            raise ValueError(f"IP address not valid {ip}")

        _LOGGER.debug(f"Initializing grill {ip} with serial number {serial_number}")

        self._ip = ip 
        self._serial_number = serial_number

    def gmg_status_response (self, value_list):
        # accept list of values from status 
        self.state = {}

        _LOGGER.debug(f"Status response raw: {value_list}")

        # grill general status
        try:
            self.state['on'] = value_list[30]
            self.state['temp'] = value_list[2]
            self.state['temp_high'] = value_list[3]
            self.state['grill_set_temp'] = value_list[6]
            self.state['grill_set_temp_high'] = value_list[7]

            # probe 1 stats
            self.state['probe1_temp'] = value_list[4]
            self.state['probe1_temp_high'] = value_list[5]
            self.state['probe1_set_temp'] = value_list[28]
            self.state['probe1_set_temp_high'] = value_list[29]
            
            # probe 2 stats
            self.state['probe2_temp'] = value_list[16]
            self.state['probe2_temp_high'] = value_list[17]
            self.state['probe2_set_temp'] = value_list[18]
            self.state['probe2_set_temp_high'] = value_list[19]

            # Grill health stats
            self.state['fireState'] = value_list[32]
            self.state['fireStatePercentage'] = value_list[33]
            self.state['warnState'] = value_list[24]

        except Exception as e:
            print(e)
            
        _LOGGER.debug(f"Status response: {self.state}") 

        return self.state

    def set_temp(self, target_temp):
        """Set the target temperature for the grill"""

        if target_temp < grill.MIN_TEMP_F or target_temp > grill.MAX_TEMP_F:
            raise ValueError(f"Target temperature {target_temp} is out of range")

        message = b'UT' + str(target_temp).encode() + b'!'

        return self.send(message)

    def set_temp_probe(self, target_temp, probe_number):
        """Set the target temperature for the grill probe"""

        if target_temp < grill.MIN_TEMP_F_PROBE or target_temp > grill.MAX_TEMP_F_PROBE:
            raise ValueError(f"Target temperature {target_temp} is out of range")
            return

        if probe_number == 1:
            message = b'UF' + str(target_temp).encode() + b'!'
        elif probe_number == 2:
            message = b'Uf' + str(target_temp).encode() + b'!'        

        return self.send(message)

    def power_on_cool(self):
        """Power on the grill to cold smoke mode"""

        message = b'UK002!'
        return self.send(message)


    def power_on(self):
        """Power on the grill"""

        message = b'UK001!'
        return self.send(message)

    def power_off(self):
        """Power off the grill"""

        message = b'UK004!'
        return self.send(message)

    def status(self):
        """Get status of grill"""

        status = None
        count = 0

        # No response from grill so resend status request but no more than 5 times
        # cannot add delay here because it will delay the whole program (Home assistant)
        while status is None or count < 5:
            status = self.send(grill.CODE_STATUS)

            # add delay of 2 seconds to allow grill to process status   
            count += 1

        if status is None:
            raise Warning("No response from grill")
               
        return self.gmg_status_response(list(status))


    def serial(self):
        """Get serial number of grill"""
        self._serial_number = self.send(grill.CODE_SERIAL).decode('utf-8')

        return self._serial_number

    def send(self, message, timeout = 1):  
        """Function to send messages via UDP to grill"""

        data = None

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)

            sock.sendto(message, (self._ip, grill.UDP_PORT))
            data, _ = sock.recvfrom(1024)
        
        except socket.timeout:
            print('timeout')
        except Exception as e: 
            print(e)
           
        return data