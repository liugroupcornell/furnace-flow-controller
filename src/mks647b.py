import time
import pyvisa as visa

class MKS647B():
    '''
    driver for MKS 647B flow controller

    communication protocal: RS-232
    '''
    def __init__(self, address:str='ASRL3::INSTR', wait_time:float=0.5,
                 range_value:int=1, range_unit:str='SLM', debug_mode:bool=False):
        rm = visa.ResourceManager()
        self.inst = rm.open_resource(address)
        self.inst.baud_rate = 9600
        self.inst.parity = visa.constants.Parity.odd
        self.inst.stop_bits = visa.constants.StopBits.one
        self.inst.data_bits = 8
        self.inst.query_delay = 0.1
        self.inst.clear()

        self.debug_mode = debug_mode

        self.wait_time = wait_time
        self.RANGE_DICT = {
            "1 SCCM": 0,
            "2 SCCM": 1,
            "5 SCCM": 2,
            "10 SCCM": 3,
            "20 SCCM": 4,
            "50 SCCM": 5,
            "100 SCCM": 6,
            "200 SCCM": 7,
            "500 SCCM": 8,
            "1 SLM": 9,
            "2 SLM": 10,
            "5 SLM": 11,
            "10 SLM": 12,
            "20 SLM": 13,
            "50 SLM": 14,
            "100 SLM": 15,
            "200 SLM": 16,
            "400 SLM": 17,
            "500 SLM": 18,
            "1 SCMM": 19,
            "1 SCFH": 20,
            "2 SCFH": 21,
            "5 SCFH": 22,
            "10 SCFH": 23,
            "20 SCFH": 24,
            "50 SCFH": 25,
            "100 SCFH": 26,
            "200 SCFH": 27,
            "500 SCFH": 28,
            "1 SCFM": 29,
            "2 SCFM": 30,
            "5 SCFM": 31,
            "10 SCFM": 32,
            "20 SCFM": 33,
            "50 SCFM": 34,
            "100 SCFM": 35,
            "200 SCFM": 36,
            "500 SCFM": 37,
            "30 SLM": 38,
            "300 SLM": 39,
        }
        self.REVERSE_RANGE_DICT = {v: k for k, v in self.RANGE_DICT.items()}
        for i in range(4):
            self.set_range(i+1, range_value, range_unit)

    def iterate_query(self, command:str):
        '''
        try a query multiple times

        Parameters
        ---
        command = command to be sent to the controller
        '''
        MAX_COUNT = 5
        val = ''
        for i in range(MAX_COUNT):
            val = self.inst.query(command)
            time.sleep(self.wait_time)

            if self.debug_mode:
                print(val)
                print(f'Executed \"{command}\" {i+1} times')
            if val[0] != 'E':
                return val

        if val[1] == '0':
            raise Exception('Channel error: An invalid channel number was \
                            specified in the command or the channel number \
                            is missing.')
        elif val[1] == '1':
            raise Exception('Unknown command: A command has been transmitted\
                             which is unknown to the 647B.')
        elif val[1] == '2':
            raise Exception('Syntax error: Only one character has been sent \
                            instead of the expected 2 byte command.')
        elif val[1] == '3':
            raise Exception('Invalid expression: The command parameter does \
                            not have decimal form, or invalid characters were \
                            found within the parameter (e.g. 100.3: the decimal \
                            point is an invalid character).')
        elif val[1] == '4':
            raise Exception('Invalid value: The transmitted parameter is \
                            outside the parameter range (e.g. 1200 is outside \
                            the range of a set point)')
        elif val[1] == '5':
            raise Exception('Autozero error: There was a trial to set the \
                            zero offset of an active channel. Before setting \
                            the zero offset, either the channel (OF #) or the \
                            gas (OF 0) has to be switched off.')
        else:
            raise Exception('Unknown error')

    def open_valve(self, channel:int):
        '''
        open valve

        Parameters
        ---
        channel = 0 means main valve
        channel = 1 through 8 means channel valve
        '''
        assert channel >= 0 and channel <= 8

        self.iterate_query(f'ON {channel}')

    def close_valve(self, channel:int):
        '''
        close valve

        Parameters
        ---
        channel = 0 means main valve
        channel = 1 through 8 means channel valve
        '''
        assert channel >= 0 and channel <= 8

        self.iterate_query(f'OF {channel}')

    def set_gas_menu(self, gas_set:int):
        '''
        select gas menu

        Parameters
        ---
        gas_set = 0 means gas menu X, normal setpoints are used
        gas_set = 1 through 5 means gas menus 1 through 5
        '''
        assert gas_set >= 0 and gas_set <= 5

        self.iterate_query(f'GM {gas_set}')

    def get_gas_menu(self):
        '''
        check for gas menu
        '''
        return int(self.iterate_query('GM R').strip())

    def set_gas_setpoint(self, channel:int, gas_set:int, set_point:float):
        '''
        enter setpoint in a gas set (may be error due to rounding)

        Parameters
        ---
        channel = 1 through 8 means channel valve
        gas_set = 1 through 5 means gas set
        set_point = full setpoint value
        '''

        range_factor = float(self.REVERSE_RANGE_DICT[self.get_range(channel)].split()[0])
        x = round(set_point / range_factor / self.get_gas_correction_factor(channel) * 1000.0)

        assert channel >= 1 and channel <= 8
        assert gas_set >= 1 and gas_set <= 5
        assert x >= 0 and x <= 1100

        self.iterate_query(f'GP {channel} {gas_set} {x:04d}')

    def get_gas_setpoint(self, channel:int, gas_set:int):
        '''
        check for setpoint in a gas set (may be error due to rounding)

        Parameters
        ---
        channel = 1 through 8 means channel valve
        gas_set = 1 through 5 means gas set
        '''
        assert channel >= 1 and channel <= 8
        assert gas_set >= 1 and gas_set <= 5

        range_factor = float(self.REVERSE_RANGE_DICT[self.get_range(channel)].split()[0])
        return round(
            float(
                self.iterate_query(f'GP {channel} {gas_set} R').strip()
            ) * self.get_gas_correction_factor(channel) / 1000.0,
            3
        ) * range_factor

    def set_flow_setpoint(self, channel:int, set_point:int):
        '''
        enter setpoint of a channel (may be error due to rounding)

        Parameters
        ---
        channel = 1 through 8 means channel valve
        set_point = full setpoint value
        '''

        range_factor = float(self.REVERSE_RANGE_DICT[self.get_range(channel)].split()[0])
        x = round(set_point / range_factor / self.get_gas_correction_factor(channel) * 1000.0)

        assert channel >= 1 and channel <= 8
        assert x >= 0 and x <= 1100

        self.iterate_query(f'FS {channel} {x:04d}')

    def get_flow_setpoint(self, channel:int):
        '''
        check for setpoint (may be error due to rounding)

        Parameters
        ---
        channel = 1 through 8 means channel valve
        '''
        assert channel >= 1 and channel <= 8

        range_factor = float(self.REVERSE_RANGE_DICT[self.get_range(channel)].split()[0])
        return round(
            float(
                self.iterate_query(f'FS {channel} R').strip()
            ) * self.get_gas_correction_factor(channel) / 1000.0,
            3
        ) * range_factor

    def get_actual_flow(self, channel:int):
        '''
        check for actual flow of a channel

        Parameters
        ---
        channel = 1 through 8 means channel valve
        '''
        assert channel >= 1 and channel <= 8

        range_factor = float(self.REVERSE_RANGE_DICT[self.get_range(channel)].split()[0])
        return int(self.iterate_query(f'FL {channel}').strip()) / 1000.0 * range_factor

    def set_range(self, channel:int, range_value:int, range_unit:str):
        '''
        enter range/scale

        Parameters
        ---
        channel = 1 through 8 means channel valve
        range_value means the desired range value
        range_unit means the desired range unit
        '''
        assert channel >= 1 and channel <= 8

        range_code = self.RANGE_DICT[f'{range_value} {range_unit}']

        assert range_code >= 0 and range_code <= 39

        self.iterate_query(f'RA {channel} {range_code:02d}')

    def get_range(self, channel:int):
        '''
        check for range/scale

        Parameters
        ---
        channel = 1 through 8 means channel valve
        '''
        assert channel >= 1 and channel <= 8

        return int(self.iterate_query(f'RA {channel} R').strip())

    def get_gas_correction_factor(self, channel:int):
        '''
        check for gas correction factor

        Parameters
        ---
        channel = 1 through 8 means channel valve
        '''
        assert channel >= 1 and channel <= 8

        return float(self.iterate_query(f'GC {channel} R').strip()) / 100.0

    def get_mode(self, channel:int):
        '''
        check for mode

        Parameters
        ---
        channel = 1 through 8 means channel valve
        '''
        assert channel >= 1 and channel <= 8

        return self.iterate_query(f'MO {channel} R').strip()

    def get_id(self):
        '''
        check for identification
        '''
        return self.iterate_query('ID').strip()


    def close(self):
        '''
        close the valves and connection
        '''
        self.close_valve(0)
        self.inst.close()