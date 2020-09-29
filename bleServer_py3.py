from bluepy.btle import Scanner, DefaultDelegate, Peripheral, BTLEDisconnectError
from time import sleep, time
from collections import deque
from random import uniform
import sys
import threading
import re

#ble stuff
bt_addrs = {"34:15:13:22:a9:be":0, "2c:ab:33:cc:68:fa":1, "34:15:13:22:96:6f":2}
bt_addrs_isConnected = {"34:15:13:22:a9:be":False, "2c:ab:33:cc:68:fa":False, "34:15:13:22:96:6f":False}
connections = {} #stores peripherals
connection_threads = {} #stores threads linked to peripherals (useless atm...)
BLE_SERVICE_UUID = "0000dfb0-0000-1000-8000-00805f9b34fb"
BLE_CHARACTERISTIC_UUID = "0000dfb1-0000-1000-8000-00805f9b34fb"
scanner = Scanner(0)
#printlock = threading.Lock()
endFlag = False
PACKET_SIZE = 19
PACKET_ZERO_OFFSET = 13500
BUFFER_SKIP = 'xxx111xxx111xxx111x'

#buffer for reassembly stuff: for handleNotification of data, store it and reassemble
# bufferQueue = []
# buffer = None
# bufferIsComplete = False
# isAcknowledged = False

'''
def pp(*arg):
    with printlock:
        for i in arg:
            print(i, end='')
            if i != len(arg)-1:
                print(' ', end='')
        print('')
'''
class BufferHandler():
    def __init__(self, number):
        self.number = str(number)
        self.bufferQueue = []
        self.buffer = None
        self.isAcknowledged = False
        self.hmap = {10:'a', 11:'b', 12:'c', 13:'d', 14:'e', 15:'f'}
    
    """
    # data is in string format, 20bytes, base30, offset13500
    # data[0] = deviceId
    # data[1:19] = xyz,pitch,roll,yaw (3bytes each)
    #data[19] = checksum -- ignore since we already validate beforehand
    # returns output (str)
    """
    def convertToDecimal(self, data):
        def base30ToDecimal(data):
            decimal = 0
            for i in range(len(data)):
                decimal *= 30
                decimal += (ord(data[i]) - 48) if data[i].isnumeric() else (ord(data[i]) - 97 + 10)
            decimal -= PACKET_ZERO_OFFSET
            return decimal
        
        if len(data) != PACKET_SIZE:
            return data
        
        # output = data[0] #str
        # output += '.'
        output = ''
        data = data[:PACKET_SIZE-1].lower() #str
        # data = data[1:PACKET_SIZE-1].lower() #str
        for i in range(0, PACKET_SIZE-2, 3):
            output += str(base30ToDecimal(data[i:i+3])) + '.'
        output = output[:-1]
        return output
        
    def is_ascii(self, s):
        return all((ord(c) < 128 and ord(c) > 47) for c in s)

    def compress(self, num):
        if num < 10:
            return num
        return num%10 ^ self.compress(num//10)
    
    def xor(self, st):
        output = 0
        for i in range(len(st)):
            output ^= ord(st[i])
        out = self.compress(output)
        return out
    
    def getChksum(self, c):
        return ord(c.lower()) - 97
    
    def checkValidity(self, data):
        #global isAcknowledged
        if not self.is_ascii(data):
            return False
        elif len(data) == 1 and data[0] == 'A': #check handshake
            self.isAcknowledged = True
            return True
        elif len(data) == PACKET_SIZE and self.getChksum(data[PACKET_SIZE-1]) == self.xor(data[:PACKET_SIZE-1]): #check valid checksum (int vs int)
            return True
        return False

    def isCompleteBuffer(self, data, msgCount):
        if self.checkValidity(data): #accepts 'A' and approved checksum packets(with len 20)
            self.bufferQueue = ''
            self.buffer = None
            return True
        if self.isAcknowledged: #if check fails, do buffering
            
            if msgCount == 2:
                if self.checkValidity(data[1:PACKET_SIZE+1]):
                    self.buffer = data[1:PACKET_SIZE+1]
                else:
                    return False
        
            output = list(filter(None, re.split(r'[\x00-\x20]', data))) #filter out nonsense bytes
            if len(output) > 0:
                assembledString = ''
                debugFlag = ''
                
                # CASE A (just right)
                # If empty, expected that len(data) > PACKET_SIZE (20)
                if len(self.bufferQueue) == 0:
                    debugFlag = '!'
                    if len(output[0]) == PACKET_SIZE+1: #valid(19) + overflow(1)
                        self.bufferQueue += output[0][PACKET_SIZE]
                        assembledString = output[0][:PACKET_SIZE]
                    debugFlag += output[0]
                    debugFlag += '!'
                # If size>0, 
                else:
                    # CASE B (perfect fit)
                    # expected that len(data) = PACKET_SIZE-1 (18)
                    # Match the single char from bufferQueue with new data
                    if len(output[0]) + len(self.bufferQueue) == PACKET_SIZE:
                        debugFlag = '@'
                        assembledString = self.bufferQueue + output[0]
                        self.bufferQueue = ''
                        debugFlag += output[0]
                        debugFlag += '@'
                    # CASE C (leftover)
                    # if handleNotification() called while processing this isCompleteBuffer()
                    # Clear previous buffer, perform rest same as CASE A
                    # Expected len(data) is 20
                    elif len(output[0]) + len(self.bufferQueue) > PACKET_SIZE:
                        if len(output[0]) + len(self.bufferQueue) > 2*PACKET_SIZE:
                            print('WTFFFFF', 'EXCEEDED 40 BYTES!!!')
                        debugFlag = '#'
                        bytesLeft = PACKET_SIZE - len(self.bufferQueue)
                        assembledString = self.bufferQueue + output[0][:bytesLeft]
                        self.bufferQueue = output[0][bytesLeft:]
                        debugFlag += output[0]
                        debugFlag += '#'
                    # CASE D (shortage)
                    # len(output[0]) + len(self.bufferQueue) < PACKET_SIZE
                    else: 
                        debugFlag = '#'
                        self.bufferQueue += output[0]
                        assembledString = BUFFER_SKIP
                        debugFlag += output[0]
                        debugFlag += '#'
                # if len(self.bufferQueue) == 0:
                    # for elem in output:
                        # debugFlag = '!'
                        # self.bufferQueue.append(elem)
                        # assembledString += elem
                # else:
                    # if len(output) == 1: #1 element in output
                        # debugFlag = '@'
                        # assembledString = self.bufferQueue.pop(0) + output[0]
                        # debugFlag += output[0]
                        # debugFlag += '@'
                    # else: #else 2 elements in output
                        # debugFlag = '#'
                        # self.bufferQueue.append(output[1])
                        # assembledString = self.bufferQueue.pop(0) + output[0]
                        # debugFlag += output[0]
                        # debugFlag += '#'
                # For debugging error packets
                # with open(f"laptopdata{self.number}.txt", "a") as text_file:
                    # print(f"F,{debugFlag}<{assembledString}>,[{self.bufferQueue}]:|{msgCount}", file=text_file)
                if self.checkValidity(assembledString):
                    self.buffer = assembledString
                    return True
        return False

class NotificationDelegate(DefaultDelegate):
    def __init__(self, number):
        DefaultDelegate.__init__(self)
        self.number = str(number)
        self.baseTime = self.pastTime = time()
        self.msgCount = self.goodPacketCount = self.goodPacketsArm = self.goodPacketsBody = 0
        self.bH = BufferHandler(number)

    def handleNotification(self, cHandle, data):
        self.msgCount += 1
        data = data.decode("utf-8")
        # print(f'{self.number} D:', data)
        # with open(f"laptopdata{self.number}.txt", "a") as text_file:
            # print(f"  {self.msgCount} D:{data}", file=text_file)
        flag = self.bH.checkValidity(data)
        if self.bH.isCompleteBuffer(data, self.msgCount):
            self.goodPacketCount += 1
            deviceId = None
            if self.bH.buffer:
                data = self.bH.buffer
                self.bH.buffer = None
                flag = 'AS'
            if flag and (self.msgCount > 1 or time() - self.baseTime > 5):
                if data[PACKET_SIZE-1].islower():
                    deviceId = 0
                    self.goodPacketsArm += 1
                else:
                    deviceId = 1
                    self.goodPacketsBody += 1
            '''
                # Prints individual report
                # Device:number,flag,deviceID:data |total|goodPacketCount|goodPacketsArm|goodPacketsBody
            '''
            data = self.bH.convertToDecimal(data)
            # with open(f"laptopdata{self.number}.txt", "a") as text_file:
                # print(f"{self.number},{flag},{deviceId}: {data} |{self.msgCount}|{self.goodPacketCount}|{self.goodPacketsArm}|{self.goodPacketsBody}", file=text_file)
        
        # Prints every 5s for debugging
        if time() - self.pastTime >= 5:
            tt = time() - self.baseTime
            print(f"---{self.number}: {tt}s have passed ---")
            with open(f"laptopdata{self.number}.txt", "a") as text_file:
                # Prints overall report
                print(f"{self.number} |{self.msgCount}|{self.goodPacketCount}|{self.goodPacketsArm}|{self.goodPacketsBody}", file=text_file)
                print(f"\n*** {tt}s have passed ***\n", file=text_file)
            self.pastTime = time()
            self.msgCount = self.goodPacketCount = self.goodPacketsArm = self.goodPacketsBody = 0

class ConnectionHandlerThread (threading.Thread):
    def __init__(self, connection_index):
        threading.Thread.__init__(self)
        self.connection_index = connection_index
        self.delay = uniform(0.1, 0.5) #Random delay
        self.isConnected = True
        self.addr = ''

    def reconnect(self, addr):
        while True: #Loop here until reconnected (Thread is doing nothing anyways...)
            try:
                print("reconnecting to", addr)
                
                devices = scanner.scan(1)
                for d in devices:
                    if d.addr in bt_addrs:
                        if bt_addrs_isConnected[d.addr]:
                            continue
                
                        p = Peripheral(addr)
                        
                        #overhead code
                        self.connection = p
                        self.connection.withDelegate(NotificationDelegate(self.connection_index))
                        self.s = self.connection.getServiceByUUID(BLE_SERVICE_UUID)
                        self.c = self.s.getCharacteristics()[0]
                        
                        connections[self.connection_index] = self.connection
                        
                        print("Reconnected to ", addr, '!')
                        self.c.write(("H").encode())
                        
                        self.isConnected = True
                        return True
            except:
                print("Error when reconnecting..")
            sleep(uniform(0.5, 0.9))
            
    def run(self):
        #Setup respective delegates, service, characteristic...
        self.connection = connections[self.connection_index]
        self.addr = self.connection.addr
        self.connection.withDelegate(NotificationDelegate(self.connection_index))
        self.s = self.connection.getServiceByUUID(BLE_SERVICE_UUID)
        self.c = self.s.getCharacteristics()[0]
        
        #Delay before HANDSHAKE
        print('Start', self.connection_index, self.c.uuid)
        sleep(self.delay)
        print('Done sleep')
        self.c.write(("H").encode())
        
        #Run thread loop forever
        while True:
            #Does continuous writing after notification if state is connected...
            if self.isConnected:
                try:
                    if self.connection.waitForNotifications(self.delay): #Executed after every handleNotification(), within the given time
                        #self.c.write(("R").encode())
                        pass
                except BTLEDisconnectError:
                    if endFlag:
                        continue
                    print("Device ", self.connection_index, " disconnected!")
                    self.isConnected = False
                    bt_addrs_isConnected[self.addr] = False
                    self.connection.disconnect()
            #Whenever state of BLE device is disconnected, run this...
            if not self.isConnected:
                print('Trying to reconnect', self.connection_index)
                if self.reconnect(self.addr):
                    print('Successfully reconnected!')
                sleep(self.delay)

## Try connecting to BLEs
def run():
    devices = scanner.scan(3)
    for d in devices:
        if d.addr in bt_addrs:
            if bt_addrs_isConnected[d.addr]:
                continue
            addr = d.addr
            idx = bt_addrs[addr]
            bt_addrs_isConnected[addr] = True
            print(addr, 'found!')
            try:
                p = Peripheral(addr)
                #connections.append(p)
                connections[idx] = p
                t = ConnectionHandlerThread(idx)
                t.daemon = True #set to true so that can CTRL-C easily
                t.start()
                connection_threads[idx] = t
            except: #Raised when unable to create connection
                print('Error in connecting device')

try:
    run()
    print('End of initial scan')
    
    #IMPT WHILE LOOP FOR KEEPING THREADS ALIVE!!!
    while True:
        pass
except KeyboardInterrupt:
    print('END OF PROGRAM. Disconnecting all devices..')
    endFlag = True