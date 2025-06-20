import can
import time
import csv
import traceback
from collections import namedtuple
from enum import Enum
from math import isfinite
import numpy as np
import warnings

import os
from collections import namedtuple
from math import isfinite

# Control mode contain {0,1,2,3,4,5,6,7} Seven eigenvalues correspond to seven control modes
# respectively
# Duty cycle mode: 0
# Current loop mode: 1
# Current brake mode: 2
# Velocity mode: 3
# Position mode: 4
# Set origin mode:5
# Position velocity loop mode :6
# Parameter dictionary for each specific motor that can be controlled with this library
# Thresholds are in the datasheet for the motor on cubemars.com
# Verified Error codes for servo motor

Servo_Params = {
        'ERROR_CODES':{
            0 : 'No Error',
            1 : 'Over temperature fault',
            2 : 'Over current fault',
            3 : 'Over voltage fault',
            4 : 'Under voltage fault',
            5 : 'Encoder fault',
            6 : 'Phase current unbalance fault (The hardware may be damaged)'
        },
        'AK10-9':{
            'P_min' : -32000,#-3200 deg
            'P_max' : 32000,#3200 deg
            'V_min' : -100000,#-100000 rpm electrical speed
            'V_max' : 100000,# 100000 rpm electrical speed
            'Curr_min':-1500,#-60A is the acutal limit but set to -15A
            'Curr_max':1500,#60A is the acutal limit but set to 15A
            'T_min' : -15,#NM
            'T_max' : 15,#NM
            'Kt_TMotor' : 0.16, # from TMotor website (actually 1/Kvll)
            'Current_Factor' : 0.59, # UNTESTED CONSTANT!
            'Kt_actual': 0.206, # UNTESTED CONSTANT!
            'GEAR_RATIO': 9.0, 
            'Use_derived_torque_constants': False, # true if you have a better model
        },
        'AK80-9':{
            'P_min' : -32000,#-3200 deg
            'P_max' : 32000,#3200 deg
            'V_min' : -32000,#-320000 rpm electrical speed
            'V_max' : 32000,# 320000 rpm electrical speed
            'Curr_min':-1500,#-60A is the acutal limit but set to -15A
            'Curr_max':1500,#60A is the acutal limit but set to 15A
            'T_min' : -30,#NM
            'T_max' : 30,#NM
            'Kt_TMotor' : 0.091, # from TMotor website (actually 1/Kvll)
            'Current_Factor' : 0.59,
            'Kt_actual': 0.115,
            'GEAR_RATIO': 9.0, 
            'NUM_POLE_PAIRS': 21,
            'Use_derived_torque_constants': False, # true if you have a better model
        },
         'AK70-10':{
            'P_min' : -32000,#-3200 deg
            'P_max' : 32000,#3200 deg
            'V_min' : -32000,#-320000 rpm electrical speed
            'V_max' : 32000,# 320000 rpm electrical speed
            'Curr_min':-1500,#-60A is the acutal limit but set to -15A
            'Curr_max':1500,#60A is the acutal limit but set to 15A
            'T_min' : -25.0,
            'T_max' : 25.0,
            'Kt_TMotor' : 0.123, # from TMotor website NM/A
            'Current_Factor' : 0.59, # # UNTESTED CONSTANT!
            'Kt_actual': 0.122, # UNTESTED CONSTANT!
            'GEAR_RATIO': 10.0,
            'NUM_POLE_PAIRS': 21,
            'Use_derived_torque_constants': False, # true if you have a better model
        },
        'CAN_PACKET_ID':{

            'CAN_PACKET_SET_DUTY':0, #Motor runs in duty cycle mode
            'CAN_PACKET_SET_CURRENT':1, #Motor runs in current loop mode
            'CAN_PACKET_SET_CURRENT_BRAKE':2, #Motor current brake mode operation
            'CAN_PACKET_SET_RPM':3, #Motor runs in current loop mode
            'CAN_PACKET_SET_POS':4, #Motor runs in position loop mode
            'CAN_PACKET_SET_ORIGIN_HERE':5, #Set origin mode
            'CAN_PACKET_SET_POS_SPD':6, #Position velocity loop mode
        },
}
"""
A dictionary with the parameters needed to control the motor
"""

class servo_motor_state:
    """Data structure to store and update motor states"""
    def __init__(self,position, velocity, current, temperature, error, acceleration):
        """
        Sets the motor state to the input.

        Args:
            position: Position in degrees
            velocity: Velocity in ERPM
            current: current in amps
            temperature: temperature in degrees C
            error: error code, 0 means no error
            acceleration: acceleration in ERPM/s
        """
        self.set_state(position, velocity, current, temperature, error, acceleration)

    def set_state(self, position, velocity, current, temperature, error, acceleration):
        """
        Sets the motor state to the input.

        Args:
            position: Position in deg
            velocity: Velocity in ERPM
            current: current in amps
            temperature: temperature in degrees C
            error: error code, 0 means no error
            acceleration: acceleration in ERPM/s
        """
        self.position = position
        self.velocity = velocity
        self.current = current
        self.temperature = temperature
        self.error = error
        self.acceleration = acceleration

    def set_state_obj(self, other_motor_state):
        """
        Sets this motor state object's values to those of another motor state object.

        Args:
            other_motor_state: The other motor state object with values to set this motor state object's values to.
        """
        self.position = other_motor_state.position
        self.velocity = other_motor_state.velocity
        self.current = other_motor_state.current
        self.temperature = other_motor_state.temperature
        self.error = other_motor_state.error
        self.acceleration = other_motor_state.acceleration

    def __str__(self):
        return 'Position: {} | Velocity: {} | Current: {} | Temperature: {} | Error: {}'.format(self.position, self.velocity, self.current, self.temperature, self.error)

# Data structure to store MIT_command that will be sent upon update
class servo_command:
    """Data structure to store Servo command that will be sent upon update"""
    def __init__(self, position, velocity, current, duty, acceleration):
        """
        Sets the motor state to the input.

        Args:
            position: Position in deg
            velocity: Velocity in ERPM
            current: Current in amps
            duty: Duty cycle in ratio (-1 to 1)
            acceleration: acceleration in ERPM/s
        """
        self.position = position
        self.velocity = velocity
        self.current = current
        self.duty = duty
        self.acceleration = acceleration

# # motor state from the controller, uneditable named tuple
# servo_motor_state = namedtuple('motor_state', 'position velocity current temperature error')
# """
# Motor state from the controller, uneditable named tuple
# """

# python-can listener object, with handler to be called upon reception of a message on the CAN bus
class motorListener(can.Listener):
    """Python-can listener object, with handler to be called upon reception of a message on the CAN bus"""
    def __init__(self, canman, motor):
        """
        Sets stores can manager and motor object references
        
        Args:
            canman: The CanManager object to get messages from
            motor: The TMotorCANManager object to update
        """
        self.canman = canman
        self.bus = canman.bus
        self.motor = motor

    def on_message_received(self, msg):
        """
        Updates this listener's motor with the info contained in msg, if that message was for this motor.

        args:
            msg: A python-can CAN message
        """
        data = bytes(msg.data)
        ID = msg.arbitration_id & 0x00000FF
        #print(ID) #uncomment this if you're not sure what the ID is and this will give you the motor ID
        if ID == self.motor.ID:
            self.motor._update_state_async(self.canman.parse_servo_message(data))

# A class to manage the low level CAN communication protocols
class CAN_Manager_servo(object):
    """A class to manage the low level CAN communication protocols"""
    debug = False
    """
    Set to true to display every message sent and recieved for debugging.
    """
    # Note, defining singletons in this way means that you cannot inherit
    # from this class, as apparently __init__ for the subclass will be called twice
    _instance = None
    """
    Used to keep track of one instantation of the class to make a singleton object
    """
    
    def __new__(cls):
        """
        Makes a singleton object to manage a socketcan_native CAN bus.
        """
        if not cls._instance:
            cls._instance = super(CAN_Manager_servo, cls).__new__(cls)
            print("Initializing CAN Manager")
            # verify the CAN bus is currently down
            os.system( 'sudo /sbin/ip link set can0 down' )
            # start the CAN bus back up
            os.system( 'sudo /sbin/ip link set can0 up type can bitrate 1000000' )
            # # increase transmit buffer length
            # os.system( 'sudo ifconfig can0 txqueuelen 1000')
            # create a python-can bus object
            cls._instance.bus = can.interface.Bus(channel='can0', bustype='socketcan')# bustype='socketcan_native')
            # create a python-can notifier object, which motors can later subscribe to
            cls._instance.notifier = can.Notifier(bus=cls._instance.bus, listeners=[])
            print("Connected on: " + str(cls._instance.bus))

        return cls._instance

    def __init__(self):
        """
        ALl initialization happens in __new__
        """
        pass
        
    def __del__(self):
        """
        # shut down the CAN bus when the object is deleted
        # This may not ever get called, so keep a reference and explicitly delete if this is important.
        """
        os.system( 'sudo /sbin/ip link set can0 down' ) 

    # subscribe a motor object to the CAN bus to be updated upon message reception
    def add_motor(self, motor):
        """
        Subscribe a motor object to the CAN bus to be updated upon message reception

        Args:
            motor: The TMotorManager object to be subscribed to the notifier
        """
        self.notifier.add_listener(motorListener(self, motor))

#* Buffer information for servo mode data manipulation

#******************START****************************#
    # Buffer allocation for 16 bit
    @staticmethod
    def buffer_append_int16( buffer,number):
        """
        buffer size for int 16

        Args:
            Buffer: memory allocated to store data.
            number: value.
        """
        buffer.append((number >> 8)&(0x00FF))
        buffer.append((number)&(0x00FF))
    
    # Buffer allocation for unsigned 16 bit
    @staticmethod
    def buffer_append_uint16( buffer,number):
        """
        buffer size for Uint 16

        Args:
            Buffer: memory allocated to store data.
            number: value.
        """
        buffer.append((number >> 8)&(0x00FF))
        buffer.append((number)&(0x00FF))
       
    # Buffer allocation for 32 bit
    @staticmethod
    def buffer_append_int32( buffer,number):
        """
        buffer size for int 32

        Args:
            Buffer: memory allocated to store data.
            number: value.
        """
        buffer.append((number >> 24)&(0x000000FF))
        buffer.append((number >> 16)&(0x000000FF))
        buffer.append((number >> 8)&(0x000000FF))
        buffer.append((number)&(0x000000FF))

    # Buffer allocation for 32 bit
    @staticmethod
    def buffer_append_uint32( buffer,number):
        """
        buffer size for uint 32

        Args:
            Buffer: memory allocated to store data.
            number: value.
        """
        buffer.append((number >> 24)&(0x000000FF))
        buffer.append((number >> 16)&(0x000000FF))
        buffer.append((number >> 8)&(0x000000FF))
        buffer.append((number)&(0x000000FF))

    # Buffer allocation for 64 bit
    @staticmethod
    def buffer_append_int64( buffer,number):
        """
        buffer size for int 64

        Args:
            Buffer: memory allocated to store data.
            number: value.
        """
        buffer.append((number >> 56)&(0x00000000000000FF))
        buffer.append((number >> 48)&(0x00000000000000FF))
        buffer.append((number >> 40)&(0x00000000000000FF))
        buffer.append((number >> 31)&(0x00000000000000FF))
        buffer.append((number >> 24)&(0x00000000000000FF))
        buffer.append((number >> 16)&(0x00000000000000FF))
        buffer.append((number >> 8)&(0x00000000000000FF))
        buffer.append((number)&(0x00000000000000FF))

    # Buffer allocation for Unsigned 64 bit
    @staticmethod
    def buffer_append_uint64( buffer,number):
        """
        buffer size for uint 64

        Args:
            Buffer: memory allocated to store data.
            number: value.
        """
        buffer.append((number >> 56)&(0x00000000000000FF))
        buffer.append((number >> 48)&(0x00000000000000FF))
        buffer.append((number >> 40)&(0x00000000000000FF))
        buffer.append((number >> 31)&(0x00000000000000FF))
        buffer.append((number >> 24)&(0x00000000000000FF))
        buffer.append((number >> 16)&(0x00000000000000FF))
        buffer.append((number >> 8)&(0x00000000000000FF))
        buffer.append((number)&(0x00000000000000FF))


#******************END****************************#

#* Sends data via CAN
    # sends a message to the motor (when the motor is in Servo mode)
    def send_servo_message(self, motor_id, data):
        """
        Sends a Servo Mode message to the motor, with a header of motor_id and data array of data

        Args:
            motor_id: The CAN ID of the motor to send to.
            data: An array of integers or bytes of data to send.
        """
        DLC = len(data)
        assert (DLC <= 8), ('Data too long in message for motor ' + str(motor_id))
        
        if self.debug:
            print('ID: ' + str(hex(motor_id)) + '   Data: ' + '[{}]'.format(', '.join(hex(d) for d in data)) )
        
        message = can.Message(arbitration_id=motor_id, data=data, is_extended_id=True)

        try:
            self.bus.send(message)
            if self.debug:
                print("    Message sent on " + str(self.bus.channel_info) )
        except can.CanError as e:
            if self.debug:
                print("    Message NOT sent: " + e.message)

    # send the power on code
    def power_on(self, motor_id):
        """
        Sends the power on code to motor_id.

        Args:
            motor_id: The CAN ID of the motor to send the message to.
            Data: This is obtained from the datasheet.
        """

        self.send_servo_message(motor_id, [ 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0XFC])
        
    # send the power off code
    def power_off(self, motor_id):
        """
        Sends the power off code to motor_id.

        Args:
            motor_id: The CAN ID of the motor to send the message to.
        """
        self.send_servo_message(motor_id, [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0XFD])


#* Code for the working of different modes in servo mode. 
   
    #* ********************START*******************************************#
    #TODO: Controller id vs motorID
    # Send Servo control message for duty cycle mode
    #*Duty cycle mode: duty cycle voltage is specified for a given motor, similar to squarewave drive mode
    def comm_can_set_duty(self, controller_id, duty):
        """
        Send a servo control message for duty cycle mode

        Args:
            controller_id: CAN ID of the motor to send the message to
            duty: duty cycle (-1 to 1) to use
        """
        buffer=[]
        self.buffer_append_int32(buffer, np.int32(duty * 100000.0))
        self.send_servo_message(controller_id|(Servo_Params['CAN_PACKET_ID']['CAN_PACKET_SET_DUTY'] << 8), buffer)

    # Send Servo control message for current loop mode
    #*Current loop mode: given the Iq current specified by the motor, the motor output torque = Iq *KT, so it can be used as a torque loop
    def comm_can_set_current(self, controller_id, current):
        """
        Send a servo control message for current loop mode

        Args:
            controller_id: CAN ID of the motor to send the message to
            current: current in Amps to use (-60 to 60)
        """
        buffer=[]
        self.buffer_append_int32(buffer, np.int32(current * 1000.0))
        self.send_servo_message(controller_id|(Servo_Params['CAN_PACKET_ID']['CAN_PACKET_SET_CURRENT'] << 8), buffer)

    # Send Servo control message for current brake mode
    #*Current brake mode: the motor is fixed at the current position by the specified brake current given by the motor (pay attention to the motor temperature when using)
    def comm_can_set_cb(self, controller_id, current):
        """
        Send a servo control message for current brake mode

        Args:
            controller_id: CAN ID of the motor to send the message to
            current: current in Amps to use (0 to 60)
        """
        buffer=[]
        self.buffer_append_int32(buffer, np.int32(current * 1000.0))
        self.send_servo_message(controller_id|(Servo_Params['CAN_PACKET_ID']['CAN_PACKET_SET_CURRENT_BRAKE'] << 8), buffer)
        
    # Send Servo control message for Velocity mode
    #*Velocity mode: the speed specified by the given motor
    def comm_can_set_erpm(self,controller_id, erpm):
        """
        Send a servo control message for velocity control mode

        Args:
            controller_id: CAN ID of the motor to send the message to
            erpm: velocity in ERPM (-100000 to 100000)
        """
        buffer=[]
        self.buffer_append_int32(buffer, np.int32(erpm))
        self.send_servo_message(controller_id| (Servo_Params['CAN_PACKET_ID']['CAN_PACKET_SET_RPM'] << 8), buffer)
    
    # Send Servo control message for Position Loop mode
    #*Position mode: Given the specified position of the motor, the motor will run to the specified position, (default speed 12000erpm acceleration 40000erpm)
    def comm_can_set_pos(self, controller_id, pos):
        """
        Send a servo control message for position control mode

        Args:
            controller_id: CAN ID of the motor to send the message to
            pos: desired position in degrees
        """
        buffer=[]
        self.buffer_append_int32(buffer, np.int32(pos * 10000.0))
        self.send_servo_message(controller_id|(Servo_Params['CAN_PACKET_ID']['CAN_PACKET_SET_POS'] << 8), buffer)
    
    #Set origin mode
    #*0 means setting the temporary origin (power failure elimination), 1 means setting the permanent zero point (automatic parameter saving), 2means restoring the default zero point (automatic parameter saving)
    def comm_can_set_origin(self, controller_id, set_origin_mode) :
        """
        set the origin

        Args:
            controller_id: CAN ID of the motor to send the message to
            set_origin_mode: 0 means setting the temporary origin (power failure elimination), 1 means setting the permanent zero point (automatic parameter saving), 2means restoring the default zero point (automatic parameter saving)
        """
        buffer=[set_origin_mode]
        self.send_servo_message(controller_id |(Servo_Params['CAN_PACKET_ID']['CAN_PACKET_SET_ORIGIN_HERE'] << 8), buffer)

    #Position and Velocity Loop Mode
    #* Check documentation
    def comm_can_set_pos_spd(self, controller_id, pos, spd, RPA ):
        """
        Send a servo control message for position control mode, with specified velocity and acceleration
        This will be a trapezoidal speed profile.

        These are the specified units from the driver user manual
        
        Args:
            controller_id: CAN ID of the motor to send the message to
            pos: desired position in degrees
            spd: desired max speed in ERPM
            RPA: desired acceleration ERPM/s
        """
        buffer=[]
        self.buffer_append_int32(buffer, (pos * 10000.0))
        self.buffer_append_int16(buffer,spd / 10)
        self.buffer_append_int16(buffer,RPA / 10)
        self.send_servo_message(controller_id |(Servo_Params['CAN_PACKET_ID']['CAN_PACKET_SET_POS_SPD'] << 8), buffer)

    #* **************************END************************************************#
 


#*****************Parsing message data********************************#
    def parse_servo_message(self, data):
        """
        Unpack the servo message into a servo_motor_state object

        Args:
            data: bytes of the message to be processed

        Returns:
            A servo_motor_state object representing the state based on the data recieved.
        """
        # using numpy to convert signed/unsigned integers
        pos_int = int.from_bytes(data[0:2], byteorder='big', signed=True)
        spd_int = int.from_bytes(data[2:4], byteorder='big', signed=True)
        cur_int = int.from_bytes(data[4:6], byteorder='big', signed=True)
        motor_pos= float( pos_int * 0.1) # motor position
        motor_spd= float( spd_int * 10.0) # motor speed
        motor_cur= float( cur_int * 0.01) # motor current
        motor_temp = int.from_bytes([data[6]], byteorder='big', signed=True) # motor temperature
        motor_error= data[7] # motor error mode
        if self.debug:
            print(data)
            print('  Position: ' + str(motor_pos))
            print('  Velocity: ' + str(motor_spd))
            print('  Current: ' + str(motor_cur))
            print('  Temp: ' + str(motor_temp))
            print('  Error: ' + str(motor_error))
            
        return servo_motor_state(motor_pos, motor_spd,motor_cur,motor_temp, motor_error, 0)


# default variables to be logged
LOG_VARIABLES = [
        "motor_position" , 
        "motor_speed" , 
        "motor_current", 
        "motor_temperature" 
]
"""
default variables to be logged
"""

# possible states for the controller
class _TMotorManState_Servo(Enum):
    """
    An Enum to keep track of different control states
    """
    DUTY_CYCLE = 0
    CURRENT_LOOP = 1
    CURRENT_BRAKE = 2
    VELOCITY = 3
    POSITION = 4
    SET_ORIGIN=5
    POSITION_VELOCITY=6
    IDLE = 7

# the user-facing class that manages the motor.
class TMotorManager_servo_can():
    """
    The user-facing class that manages the motor. This class should be
    used in the context of a with as block, in order to safely enter/exit
    control of the motor.
    """
    def __init__(self, motor_type='AK80-9', motor_ID=1, max_mosfett_temp = 50, CSV_file=None, log_vars = LOG_VARIABLES):
        """
        Sets up the motor manager. Note the device will not be powered on by this method! You must
        call __enter__, mostly commonly by using a with block, before attempting to control the motor.

        Args:
            motor_type: The type of motor being controlled, ie AK80-9.
            motor_ID: The CAN ID of the motor.
            max_mosfett_temp: temperature of the mosfett above which to throw an error, in Celsius
            CSV_file: A CSV file to output log info to. If None, no log will be recorded.
            log_vars: The variables to log as a python list. The full list of possibilities is
                - "output_angle"
                - "output_velocity"
                - "output_acceleration"
                - "current"
                - "output_torque"
                - "motor_angle"
                - "motor_velocity"
                - "motor_acceleration"
                - "motor_torque"
        """
        self.type = motor_type
        self.ID = motor_ID
        self.csv_file_name = CSV_file
        self.max_temp = max_mosfett_temp # max temp in deg C, can update later
        print("Initializing device: " + self.device_info_string())

        self._motor_state = servo_motor_state(0.0,0.0,0.0,0.0,0.0,0.0)
        self._motor_state_async = servo_motor_state(0.0,0.0,0.0,0.0,0.0,0.0)
        self._command = servo_command(0.0,0.0,0.0,0.0,0.0)
        self._control_state = _TMotorManState_Servo.IDLE

        self._entered = False
        self._start_time = time.time()
        self._last_update_time = self._start_time
        self._last_command_time = None
        self._updated = False
        
        self.log_vars = log_vars
        self.LOG_FUNCTIONS = {
            "motor_position" : self.get_motor_angle_degrees, 
            "motor_speed" : self.get_motor_velocity_rpm, 
            "motor_current" : self.get_current_qaxis_amps, 
            "motor_temperature" : self.get_temperature_celsius,
        }
        
        self._canman = CAN_Manager_servo()
        self._canman.add_motor(self)
               
    def __enter__(self):
        """
        Used to safely power the motor on and begin the log file.
        """
        print('Turning on control for device: ' + self.device_info_string())
        if self.csv_file_name is not None:
            with open(self.csv_file_name,'w') as fd:
                writer = csv.writer(fd)
                writer.writerow(["pi_time"]+self.log_vars)
            self.csv_file = open(self.csv_file_name,'a').__enter__()
            self.csv_writer = csv.writer(self.csv_file)
        self.power_on() #TODO: How to control this?
        self._send_command()
        self._entered = True
        if not self.check_can_connection():
            raise RuntimeError("Device not connected: " + str(self.device_info_string()))
        return self

    def __exit__(self, etype, value, tb):
        """
        Used to safely power the motor off and close the log file.
        """
        print('Turning off control for device: ' + self.device_info_string())
        self.power_off()#TODO: How to control this

        if self.csv_file_name is not None:
            self.csv_file.__exit__(etype, value, tb)

        if not (etype is None):
            traceback.print_exception(etype, value, tb)


    # this method is called by the handler every time a message is recieved on the bus
    # from this motor, to store the most recent state information for later
    def _update_state_async(self, servo_state):
        """
        This method is called by the handler every time a message is recieved on the bus
        from this motor, to store the most recent state information for later
        
        Args:
            servo_state: the servo_state object with the updated motor state

        Raises:
            RuntimeError when device sends back an error code that is not 0 (0 meaning no error)
        """
        if servo_state.error != 0:
            raise RuntimeError('Driver board error for device: ' + self.device_info_string() + ": " + Servo_Params['ERROR_CODES'][servo_state.error])

        now = time.time()
        dt = self._last_update_time - now
        self._last_update_time = now
        self._motor_state_async.acceleration = (servo_state.velocity - self._motor_state_async.velocity)/dt
        self._motor_state_async.set_state_obj(servo_state)
        self._updated = True

    
    # this method is called by the user to synchronize the current state used by the controller
    # with the most recent message recieved
    def update(self):
        """
        This method is called by the user to synchronize the current state used by the controller/logger
        with the most recent message recieved, as well as to send the current command.
        """
        # check that the motor is safely turned on
        if not self._entered:
            raise RuntimeError("Tried to update motor state before safely powering on for device: " + self.device_info_string())

        if self.get_temperature_celsius() > self.max_temp:
            raise RuntimeError("Temperature greater than {}C for device: {}".format(self.max_temp, self.device_info_string()))
        # check that the motor data is recent
        now = time.time()
        if (now - self._last_command_time) < 0.25 and ( (now - self._last_update_time) > 0.1):
            warnings.warn("State update requested but no data from motor. Delay longer after zeroing, decrease frequency, or check connection. " + self.device_info_string(), RuntimeWarning)
        else:
            self._command_sent = False

        self._motor_state.set_state_obj(self._motor_state_async)
        
        # send current motor command
        self._send_command()

        # writing to log file
        if self.csv_file_name is not None:
            self.csv_writer.writerow([self._last_update_time - self._start_time] + [self.LOG_FUNCTIONS[var]() for var in self.log_vars])

        self._updated = False
        
    # sends a command to the motor depending on whats controlm mode the motor is in
    def _send_command(self):
        """
        Sends a command to the motor depending on whats controlm mode the motor is in. This method
        is called by update(), and should only be called on its own if you don't want to update the motor state info.
        """
        if self._control_state == _TMotorManState_Servo.DUTY_CYCLE:
            self._canman.comm_can_set_duty(self.ID,self._command.duty)
        elif self._control_state == _TMotorManState_Servo.CURRENT_LOOP:
            self._canman.comm_can_set_current(self.ID,self._command.current)
        elif self._control_state == _TMotorManState_Servo.CURRENT_BRAKE:
            self._canman.comm_can_set_cb(self.ID,self._command.current)
        elif self._control_state == _TMotorManState_Servo.VELOCITY:
            self._canman.comm_can_set_rpm(self.ID, self._command.velocity)
        elif self._control_state == _TMotorManState_Servo.POSITION:
            self._canman.comm_can_set_pos(self.ID, self._command.position, 0 , 0) #set pos requires args for vel, acc even if they will not be used
        elif self._control_state == _TMotorManState_Servo.POSITION_VELOCITY:
            self._canman.comm_can_set_pos_spd(self.ID, self._command.position, self._command.velocity, self._command.acceleration)
        elif self._control_state == _TMotorManState_Servo.IDLE:
            self._canman.comm_can_set_current(self.ID, 0.0)

        #TODO:Add other modes
        else:
            raise RuntimeError("UNDEFINED STATE for device " + self.device_info_string())

        self._last_command_time = time.time()

    # Basic Motor Utility Commands
    def power_on(self):
        """Powers on the motor."""
        self._canman.power_on(self.ID)
        self._updated = True

    def power_off(self):
        """Powers off the motor."""
        self._canman.power_off(self.ID)

    # zeros the position
    def set_zero_position(self):
        """Zeros the position"""
        self._canman.comm_can_set_origin(self.ID,0)
        self._last_command_time = time.time()

    # getters for motor state
    def get_temperature_celsius(self):
        """
        Returns:
            The most recently updated motor temperature in degrees C.
        """
        return self._motor_state.temperature
    
    def get_motor_error_code(self):
        """
        Returns:
            The most recently updated motor error code.
            Note the program should throw a runtime error before you get a chance to read
            this value if it is ever anything besides 0.

        Codes:
            0 : 'No Error',
            1 : 'Over temperature fault',
            2 : 'Over current fault',
            3 : 'Over voltage fault',
            4 : 'Under voltage fault',
            5 : 'Encoder fault',
            6 : 'Phase current unbalance fault (The hardware may be damaged)'
        """
        return self._motor_state.error

    def get_current_qaxis_amps(self):
        """
        Returns:
            The most recently updated qaxis current in amps
        """
        return self._motor_state.current

    def get_output_angle_degrees(self):
        """
        Returns:
            The most recently updated output angle in degrees
        """
        return self._motor_state.position

    def get_output_velocity_rpm(self):
        """
        Returns:
            The most recently updated output velocity in RPM
        """
        return self._motor_state.velocity / Servo_Params[self.type]["NUM_POLE_PAIRS"] #convert ERPM to RPM

    def get_output_acceleration_radians_per_second_squared(self):
        """
        Returns:
            The most recently updated output acceleration in radians per second per second
        """
        return (self._motor_state.acceleration / Servo_Params[self.type]["NUM_POLE_PAIRS"]) * ((2*np.pi)/60) #convert from ERPM/s to rad/s^2

    def get_output_torque_newton_meters(self):
        """
        Returns:
            the most recently updated output torque in Nm
        """
        return self.get_current_qaxis_amps()*Servo_Params[self.type]["Kt_actual"]*Servo_Params[self.type]["GEAR_RATIO"]

    def enter_duty_cycle_control(self):
        """
        Must call this to enable sending duty cycle commands.
        """
        self._control_state = _TMotorManState_Servo.DUTY_CYCLE

    def enter_current_control(self):
        """
        Must call this to enable sending current commands.
        """
        self._control_state = _TMotorManState_Servo.CURRENT_LOOP

    def enter_current_brake_control(self):
        """
        Must call this to enable sending current brake commands.
        """
        self._control_state = _TMotorManState_Servo.CURRENT_BRAKE

    def enter_velocity_control(self):
        """
        Must call this to enable sending velocity commands.
        """
        self._control_state = _TMotorManState_Servo.VELOCITY

    def enter_position_control(self):
        """
        Must call this to enable position commands.
        """
        self._control_state = _TMotorManState_Servo.POSITION

    def enter_position_velocity_control(self):
        """
        Must call this to enable sending position commands with specified velocity and accleration limits.
        """
        self._control_state = _TMotorManState_Servo.POSITION_VELOCITY

    def enter_idle_mode(self):
        """
        Enter the idle state, where duty cycle is set to 0. (This is the default state.)
        """
        self._control_state = _TMotorManState_Servo.IDLE

    # used for either impedance or MIT mode to set output angle
    def set_output_angle_degrees(self, pos, vel, acc):
        """
        Update the current command to the desired position, when in position or position-velocity mode.
        Note, this does not send a command, it updates the TMotorManager's saved command,
        which will be sent when update() is called.
        
        These are the specified units from the driver user manual

        Args:
            pos: The desired output angle in deg 
            vel: The desired speed to get there in ERPM (when in POSITION_VELOCITY mode)
            acc: The desired acceleration to get there in ERPM/s (when in POSITION_VELOCITY mode)
        """
        if np.abs(pos) >= Servo_Params[self.type]["P_max"]:
            raise RuntimeError("Cannot control using impedance mode for angles with magnitude greater than " + str(Servo_Params[self.type]["P_max"]) + "degrees!")
        
        if self._control_state == _TMotorManState_Servo.POSITION_VELOCITY:
            self._command.position = pos
            self._command.velocity = vel
            self._command.acceleration = acc
        elif self._control_state == _TMotorManState_Servo.POSITION:
            self._command.position = pos
        else:
            raise RuntimeError("Attempted to send position command without entering position control " + self.device_info_string()) 

    def set_duty_cycle_percent(self, duty):
        """
        Used for duty cycle mode, to set desired duty cycle.
        Note, this does not send a command, it updates the TMotorManager's saved command,
        which will be sent when update() is called.

        Args:
            duty: The desired duty cycle, (-100 to 100) percent
        """
        duty = duty/100 #convert to fraction
        if self._control_state not in [_TMotorManState_Servo.DUTY_CYCLE]:
            raise RuntimeError("Attempted to send duty cycle command without gains for device " + self.device_info_string()) 
        else:
            if np.abs(duty) > 1:
                raise RuntimeError("Cannot control using duty cycle mode for duty cycles greater than 100%!")
            self._command.duty = duty

    def set_output_velocity_rpm(self, vel):
        """
        Used for velocity mode to set output velocity command.
        Note, this does not send a command, it updates the TMotorManager's saved command,
        which will be sent when update() is called.

        Args:
            vel: The desired output speed in RPM
        """
        vel = vel*(Servo_Params[self.type]["NUM_POLE_PAIRS"]) # convert to ERPM
        if np.abs(vel) >= Servo_Params[self.type]["V_max"]:
            raise RuntimeError("Cannot control using speed mode for angles with magnitude greater than " + str(Servo_Params[self.type]["V_max"]) + "ERPM!")

        if self._control_state not in [_TMotorManState_Servo.VELOCITY]:
            raise RuntimeError("Attempted to send speed command without gains for device " + self.device_info_string()) 
        self._command.velocity = vel #in ERPM

    # used for either current MIT mode to set current
    def set_motor_current_qaxis_amps(self, current):
        """
        Used for current mode to set current command.
        Note, this does not send a command, it updates the TMotorManager's saved command,
        which will be sent when update() is called.
        
        Args:
            current: the desired current in amps.
        """
        if self._control_state not in [_TMotorManState_Servo.CURRENT_LOOP, _TMotorManState_Servo.CURRENT_BRAKE]:
            raise RuntimeError("Attempted to send current command before entering current mode for device " + self.device_info_string()) 
        self._command.current = current

    # used for either current or MIT Mode to set current, based on desired torque
    def set_output_torque_newton_meters(self, torque):
        """
        Used for current mode to set current, based on desired torque.
        If a more complicated torque model is available for the motor, that will be used.
        Otherwise it will just use the motor's torque constant.
        
        Args:
            torque: The desired output torque in Nm.
        """
        self.set_motor_current_qaxis_amps((torque/Servo_Params[self.type]["Kt_actual"]/Servo_Params[self.type]["GEAR_RATIO"]) )

    # motor-side functions to account for the gear ratio
    def set_motor_torque_newton_meters(self, torque):
        """
        Wrapper of set_output_torque that accounts for gear ratio to control motor-side torque
        
        Args:
            torque: The desired motor-side torque in Nm.
        """
        self.set_output_torque_newton_meters(torque*Servo_Params[self.type]["GEAR_RATIO"])

    def set_motor_angle_degrees(self, pos):
        """
        Wrapper for set_output_angle that accounts for gear ratio to control motor-side angle
        
        Args:
            pos: The desired motor-side position in degrees.
        """
        self.set_output_angle_degrees(pos/(Servo_Params[self.type]["GEAR_RATIO"]),0,0)

    def set_motor_velocity_rpm(self, vel):
        """
        Wrapper for set_output_velocity that accounts for gear ratio to control motor-side velocity
        
        Args:
            vel: The desired motor-side velocity in rad/s.
        """
        self.set_output_velocity_rpm(vel/(Servo_Params[self.type]["GEAR_RATIO"]))

    def get_motor_angle_degrees(self):
        """
        Wrapper for get_output_angle that accounts for gear ratio to get motor-side angle
        
        Returns:
            The most recently updated motor-side angle in rad.
        """
        return self.get_output_angle_degrees()*Servo_Params[self.type]["GEAR_RATIO"]

    def get_motor_velocity_rpm(self):
        """
        Wrapper for get_output_velocity that accounts for gear ratio to get motor-side velocity
        
        Returns:
            The most recently updated motor-side velocity in RPM.
        """
        return self.get_output_velocity_rpm()*Servo_Params[self.type]["GEAR_RATIO"]

    def get_motor_acceleration_radians_per_second_squared(self):
        """
        Wrapper for get_output_acceleration that accounts for gear ratio to get motor-side acceleration
        
        Returns:
            The most recently updated motor-side acceleration in rad/s/s.
        """
        return self.get_output_acceleration_radians_per_second_squared()*Servo_Params[self.type]["GEAR_RATIO"]

    def get_motor_torque_newton_meters(self):
        """
        Wrapper for get_output_torque that accounts for gear ratio to get motor-side torque
        
        Returns:
            The most recently updated motor-side torque in Nm.
        """
        return self.get_output_torque_newton_meters()/Servo_Params[self.type]["GEAR_RATIO"]

    # Pretty stuff
    def __str__(self):
        """Prints the motor's device info and current"""
        return self.device_info_string() + " | Position: " + '{: 1f}'.format(round(self.position,3)) + " deg | Velocity: " + '{: 1f}'.format(round(self.velocity,3)) + " ERPM | current: " + '{: 1f}'.format(round(self.current_qaxis,3)) + " A | temp: " + '{: 1f}'.format(round(self.temperature,0)) + " C"

    def device_info_string(self):
        """Prints the motor's ID and device type."""
        return str(self.type) + "  ID: " + str(self.ID)

    # Checks the motor connection by sending a 10 commands and making sure the motor responds.
    def check_can_connection(self):
        """
        Checks the motor's connection by attempting to send 10 startup messages.
        If it gets 10 replies, then the connection is confirmed.

        Returns:
            True if a connection is established and False otherwise.
        """
        if not self._entered:
            raise RuntimeError("Tried to check_can_connection before entering motor control! Enter control using the __enter__ method, or instantiating the TMotorManager in a with block.")
        Listener = can.BufferedReader()
        self._canman.notifier.add_listener(Listener)
        for i in range(10):
            self.power_on()
            time.sleep(0.001)
        success = True
        # time.sleep(0.1)
        # for i in range(10):
        #     if Listener.get_message(timeout=0.1) is None:
        #         success = False
        # self._canman.notifier.remove_listener(Listener)
        return success

    # controller variables
    temperature = property(get_temperature_celsius, doc="temperature_degrees_C")
    """Temperature in Degrees Celsius"""

    error = property(get_motor_error_code, doc="temperature_degrees_C")
    """Motor error code. 0 means no error.
    
    Codes:
        0 : 'No Error',
        1 : 'Over temperature fault',
        2 : 'Over current fault',
        3 : 'Over voltage fault',
        4 : 'Under voltage fault',
        5 : 'Encoder fault',
        6 : 'Phase current unbalance fault (The hardware may be damaged)'
    """

    # electrical variables
    current_qaxis = property(get_current_qaxis_amps, set_motor_current_qaxis_amps, doc="current_qaxis_amps_current_only")
    """Q-axis current in amps"""

    # output-side variables
    position = property(get_output_angle_degrees, set_output_angle_degrees, doc="output_angle_radians_impedance_only")
    """Output angle in rad"""

    velocity = property (get_output_velocity_rpm, set_output_velocity_rpm, doc="output_velocity_radians_per_second")
    """Output velocity in rad/s"""

    acceleration = property(get_output_acceleration_radians_per_second_squared, doc="output_acceleration_radians_per_second_squared")
    """Output acceleration in rad/s/s"""

    torque = property(get_output_torque_newton_meters, set_output_torque_newton_meters, doc="output_torque_newton_meters")
    """Output torque in Nm"""

    # motor-side variables
    angle_motorside = property(get_motor_angle_degrees, set_motor_angle_degrees, doc="motor_angle_radians_impedance_only")
    """Motor-side angle in rad"""
    
    velocity_motorside = property (get_motor_velocity_rpm, set_motor_velocity_rpm, doc="motor_velocity_radians_per_second")
    """Motor-side velocity in rad/s"""

    acceleration_motorside = property(get_motor_acceleration_radians_per_second_squared, doc="motor_acceleration_radians_per_second_squared")
    """Motor-side acceleration in rad/s/s"""

    torque_motorside = property(get_motor_torque_newton_meters, set_motor_torque_newton_meters, doc="motor_torque_newton_meters")
    """Motor-side torque in Nm"""


