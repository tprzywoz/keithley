import serial
import time

class PicoAmp:
    def __init__(self, logger, port="ttyUSB0", stub=0):
        self.stub = stub
        self.logger = logger
        if not stub:
            self.open_serial(port)
            self.verify()
        
                    
    def open_serial(self, port=None):
        # self.ser = serial.Serial(
            # port = "/dev/"+port,
            # baudrate=9600,
        # )
        # self.logger.info("Pico Amp: serial open")
        i=0
        while i<=10:
            try:
                self.ser = serial.Serial(
                    port = "/dev/ttyUSB" + str(i),
                    baudrate=9600,
                )
                self.logger.info("Pico Amp: serial open")
                break
            except:
                self.logger.error("Pico Amp: serial open failed {}".format(i))
                i += 1
                
    def verify(self):
        self.write('*RST')
        self.write('*IDN?')
        time.sleep(1)
        id = self.ser.read_all()
        print(id)
        if str(id)[2:-36] == 'KEITHLEY INSTRUMENTS INC.,MODEL 6487,4563048,B04':
            self.logger.info("Pico Amp: id correct")
            self.logger.info("ID: "+ str(id))
        else:
            self.logger.error("Pico Amp: ID read failed:")
            self.logger.error(id)
                            
    def write(self, value):
        self.logger.debug("PicoAmmeter: " + str(value))
        if not self.stub:
            self.ser.write(value.encode(encoding="utf-8")  + bytes([0x0D]))
            
    def read(self, value):
        self.logger.info("PicoAmmeter: " + value)
        if not self.stub:
            self.ser.write(value)
            time.sleep(1)
            readout = self.ser.read_all()
            self.logger.info("Readout: " + readout)
            return readout
        else:
            return '0'
    
    def set_SMU(self, value): #TODO interlock must be implemented: check when to put input with information to connect/disconnect interlock
        self.write("*RST")
        self.write("SOUR:VOLT:RANG 50")
        self.write("SOUR:VOLT {}".format(value))
        self.write("SOUR:VOLT:ILIM 2.5e-3")
        # input("Check output voltage")
        # Do we really want this?:
        self.write("SYST:ZCH OFF")
        self.write("ARM:COUN INF")
        self.write("SOUR:VOLT:SWE:STAR 0")
        self.write("SOUR:VOLT:SWE:STOP {}".format(value))
        self.write("SOUR:VOLT:SWE:STEP 1")
        self.write("SOUR:VOLT:SWE:DEL 1")
        self.write("SOUR:VOLT:SWE:INIT") # Tu uruchamia się ouput ale pozostaje na wartości START
        # input("Check output voltage: befor init:imm")
        self.write("INIT:IMM") # To realnie porusza sweepem w całym zakresie jeśli jest ARM:COUN INF. W przeciwnym wypadku
        #każda taka komenda = 1 krok sweep
        
    def set_SMU2(self, value):
        self.write("*RST")
        self.write("SOUR:VOLT:RANG 10")
        self.write("SOUR:VOLT {}".format(value))
        self.write("SOUR:VOLT:ILIM 2.5e-3")
        # input("Check output voltage")
        self.write("SOUR:VOLT:STAT ON")
        # input("Check output voltage")
        self.write("SOUR:VOLT {}".format(value+1))
        # input("Check output voltage")
        
    # SMU output on/off (WARNING off means VOUT=0, not HI)
    def output(self, state):
        if state:
            self.write("SOUR:VOLT:STAT ON")
        else:
            self.write("SOUR:VOLT:STAT OFF")
            
    # SMU output value: use only to change value of active output of SMU
    def set_amplitude(self, v):
        self.write("SOUR:VOLT {}".format(v))


    def prepare_meas_amp(self):
        self.write("FUNC 'CURR'")
        self.write("SYST:ZCH ON")
        self.write("CURR:RANG 2e-9")
        self.write("INIT")
        
        self.write("SYST:ZCOR:STAT OFF")
        self.write("SOUR:VOLT:SWE:STOP {}")
        self.write("SYST:ZCOR:ACQ")
        self.write("SYST:ZCOR ON")
        
        self.write("CURR:RANG:AUTO ON")

        
    def meas_amp(self):
        self.prepare_meas_amp()
        self.write("SYST:ZCH OFF")
        return self.read("READ?")
     
        
    def get_voltage(self):
        return self.read("SOUR:AMPLITUDE ?")
        

#TODO verify it
if __name__ == '__main__':
    import logging
    logger = logging.getLogger("__name__")
    inst = PicoAmp(logger)
    inst.set_SMU(8)
    input("VOUT = 8V")
    inst.set_SMU(15)
    print(inst.get_voltage()) #TODO change data format to float