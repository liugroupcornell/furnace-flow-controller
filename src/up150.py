import time
import pyvisa as visa

class UP150():
    '''
    driver for Yokogawa temperature controller UP150
    
    communication protocal: RS-485, PC Link
    '''
    def __init__(self, address:str='ASRL4::INSTR', wait_time:float=0.7):
        rm = visa.ResourceManager()
        self.inst = rm.open_resource(address)
        self.inst.baud_rate = 9600
        self.inst.parity = visa.constants.Parity.none
        self.inst.stop_bits = visa.constants.StopBits.one
        self.inst.data_bits = 8
        self.inst.query_delay = 0.1
        self.inst.clear()
        
        self.wait_time = wait_time

        self.set_start_setpoint()
        self.clear_sp_tm()

    def buffer_read(self)->str:
        '''
        read buffer
        '''
        num_bytes = self.inst.bytes_in_buffer
        return self.inst.read_bytes(num_bytes)
    
    def calculate_xor(self, data: bytes) -> int:
        checksum = 0
        for b in data:
            checksum ^= b
        return checksum
    
    def get_current_temp(self) -> int:
        '''
        get current temperature value

        Return
        ---
        current temperature value: `int`, unit: Celsius
        '''
        cmd = b'\x02' + b'01010WRDD0002,01' + b'\x03' + b'\r'
        self.inst.write_raw(cmd)
        time.sleep(self.wait_time)

        reply = self.buffer_read()
        return int(reply[7:11], 16)
    
    def get_current_setpoint(self) -> int:
        '''
        get setpoint temperature value

        Return
        ---
        setpoint temperature value: `int`, unit: Celsius
        '''
        cmd = b'\x02' + b'01010WRDD0003,01' + b'\x03' + b'\r'
        self.inst.write_raw(cmd)
        time.sleep(self.wait_time)

        reply = self.buffer_read()
        return int(reply[7:11], 16) # hex to int transform
    
    def get_segment_time_left(self) -> int:
        '''
        get segment time left

        Return
        ---
        segment time left: `int`, unit: minutes
        '''
        cmd = b'\x02' + b'01010WRDD0008,01' + b'\x03' + b'\r'
        self.inst.write_raw(cmd)
        time.sleep(self.wait_time)

        reply = self.buffer_read()
        return int(reply[7:11], 16)
    
    def get_segment_number(self) -> int:
        '''
        get program segment number

        Return
        ---
        segment number: `int`
        '''
        cmd = b'\x02' + b'01010WRDD0010,01' + b'\x03' + b'\r'
        self.inst.write_raw(cmd)
        time.sleep(self.wait_time)

        reply = self.buffer_read()
        return int(reply[7:11], 16)
    
    def set_reset(self):
        '''
        reset/stop furnace
        '''
        cmd = b'\x02' + b'01010WWRD0121,01,0000' + b'\x03' + b'\r'
        self.inst.write_raw(cmd)
        time.sleep(self.wait_time)
        return self.buffer_read()

    def set_run(self):
        '''
        run furnace
        '''
        cmd = b'\x02' + b'01010WWRD0121,01,0001' + b'\x03' + b'\r'
        self.inst.write_raw(cmd)
        time.sleep(self.wait_time)
        return self.buffer_read()

    def set_start_setpoint(self, temp:int=25):
        '''
        set start setpoint temperature

        Parameters
        ---
        temp: `int`, setpoint temperature, from 0 to 1200, unit: Celsius
        '''
        assert temp >= 0 and temp <= 1200

        cmd = b'\x02' + b'01010WWRD0228,01,' + f'{temp:04X}'.encode('ascii') + b'\x03' + b'\r'
        self.inst.write_raw(cmd)
        time.sleep(self.wait_time)
        return self.buffer_read()

    def set_sp_setpoint(self, num:int, temp:int):
        '''
        set segment setpoint temperature
        
        Parameters
        ---
        num: `int`, segment number, from 1 to 16
        temp: `int`, setpoint temperature, from 0 to 1200, unit: Celsius
        '''
        assert num >= 1 and num <= 16
        assert temp >= 0 and temp <= 1200

        num = 27 + num*2
        cmd = b'\x02' + b'01010WWRD02' + f'{num:02d}'.encode('ascii') + b',01,' \
            + f'{temp:04X}'.encode('ascii') + b'\x03' + b'\r'
        self.inst.write_raw(cmd)
        time.sleep(self.wait_time)
        return self.buffer_read()
    
    def get_sp_setpoint(self, num:int) -> int:
        '''
        get segment setpoint temperature

        Parameters
        ---
        num: `int`, segment number, from 1 to 16

        Return
        ---
        segment setpoint temperature: `int`, unit: Celsius
        '''
        assert num >= 1 and num <= 16

        num = 27 + num*2
        cmd = b'\x02' + b'01010WRDD02' + f'{num:02d}'.encode('ascii') + b',01' + b'\x03' + b'\r'
        self.inst.write_raw(cmd)
        time.sleep(self.wait_time)

        reply = self.buffer_read()
        return int(reply[7:11], 16) # hex to int transform

    def set_tm_length(self, num:int, length:int):
        '''
        set segment time

        Parameters
        ---
        num: `int`, time event number, from 1 to 16
        length: `int`, time event length, unit: minutes
        '''
        assert num >= 1 and num <= 16
        
        num = 28 + num*2
        cmd = b'\x02' + b'01010WWRD02' + f'{num:02d}'.encode('ascii') + b',01,' \
            + f'{length:04X}'.encode('ascii') + b'\x03' + b'\r'
        self.inst.write_raw(cmd)
        time.sleep(self.wait_time)
        return self.buffer_read()
    
    def get_tm_length(self, num:int) -> int:
        '''
        get segment time

        Parameters
        ---
        num: `int`, time event number, from 1 to 16

        Return
        ---
        segment time: `int`, unit: minutes
        '''
        assert num >= 1 and num <= 16

        num = 28 + num*2
        cmd = b'\x02' + b'01010WRDD02' + f'{num:02d}'.encode('ascii') + b',01' + b'\x03' + b'\r'
        self.inst.write_raw(cmd)
        time.sleep(self.wait_time)

        reply = self.buffer_read()
        return int(reply[7:11], 16) # hex to int transform
    
    def clear_sp_tm(self):
        '''
        clear all setpoint and time
        '''
        for i in range(1, 17):
            self.set_sp_setpoint(i, 0)
            self.set_tm_length(i, 0)
        self.inst.clear()

    def close(self):
        self.set_reset()
        self.inst.close()