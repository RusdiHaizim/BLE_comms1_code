from bluepy.btle import Scanner, DefaultDelegate, Peripheral, BTLEDisconnectError
from time import sleep, time
from collections import deque
from random import uniform
import sys
import threading
import re

#ble stuff
bt_addrs = {"34:15:13:22:a9:be":0, "2c:ab:33:cc:68:fa":1, "34:15:13:22:96:6f":2}
connections = {} #stores peripherals
connection_threads = {} #stores threads linked to peripherals (useless atm...)
BLE_SERVICE_UUID = "0000dfb0-0000-1000-8000-00805f9b34fb"
BLE_CHARACTERISTIC_UUID = "0000dfb1-0000-1000-8000-00805f9b34fb"
scanner = Scanner(0)
#printlock = threading.Lock()
endFlag = False

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
        self.bufferIsComplete = False
        self.isAcknowledged = False

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
        return self.compress(output)

    def checkValidity(self, data):
        #global isAcknowledged
        if not self.is_ascii(data):
            return False
        elif len(data) == 1 and data[0] == 'A':
            self.isAcknowledged = True
            return True
        elif len(data) == 20 and data[19] == str(self.xor(data[:19])):
            # print(data[19], 'vs',str(xor(data[19])))
            return True
        return False

    def isCompleteBuffer(self, data):
        if self.checkValidity(data): #accepts 'A' and approved checksum packets(with len 20)
            return True
        if self.isAcknowledged: #if check fails, do buffering
            output = list(filter(None, re.split(r'[\x00-\x20]', data))) #filter out nonsense bytes
            if len(output) > 0:
                assembledString = ''
                if len(self.bufferQueue) == 0:
                    for elem in output:
                        assembledString += '!'
                        self.bufferQueue.append(elem)
                        assembledString += elem
                else:
                    if len(output) == 1: #1 element in output
                        assembledString = self.bufferQueue.pop(0) + output[0]
                    else: #else 2 elements in output
                        self.bufferQueue.append(output[1])
                        assembledString = self.bufferQueue.pop(0) + output[0]
                # print('regex:', assembledString, self.bufferQueue)
                if self.checkValidity(assembledString):
                    self.buffer = assembledString
                    # print('WHEW', self.bH.buffer)
                    return True
        return False

class NotificationDelegate(DefaultDelegate):
    def __init__(self, number):
        DefaultDelegate.__init__(self)
        self.number = str(number)
        self.pastTime = time()
        self.msgCount = self.goodPacketCount = self.goodPacketsArm = self.goodPacketsBody = 0
        self.bH = BufferHandler(number)

    def handleNotification(self, cHandle, data):
        #global buffer
        self.msgCount += 1
        data = data.decode("utf-8")
        # print(f'{self.number} D:', data)
        flag = self.bH.checkValidity(data)
        if self.bH.isCompleteBuffer(data):
            self.goodPacketCount += 1
            if data[0] == '0':
                self.goodPacketsArm += 1
            elif data[0] == '1':
                self.goodPacketsBody += 1
            if self.bH.buffer:
                if data[0] != '0' and self.bH.buffer[0] == '0':
                    if data[0] == '1':
                        self.goodPacketsBody -= 1
                    self.goodPacketsArm += 1
                elif data[0] != '1' and self.bH.buffer[0] == '1':
                    if data[0] == '0':
                        self.goodPacketsArm -= 1
                    self.goodPacketsBody += 1
                data = self.bH.buffer
                flag = 'Assembled!'
                # print(buffer)
                # with open("laptopdata.txt", "a") as text_file:
                    # print(f"!{flag}: {data} | {self.msgCount}", file=text_file)
                self.bH.buffer = None
            # print(f"{flag}: {data} | {self.msgCount} |{self.goodPacketCount}|{self.goodPacketsArm}|{self.goodPacketsBody}")
            with open(f"laptopdata{self.number}.txt", "a") as text_file:
                '''
                # Device:number,flag:data |total|goodPacketCount|goodPacketsArm|goodPacketsBody
                '''
                print(f"{self.number},{flag}: {data} |{self.msgCount}|{self.goodPacketCount}|{self.goodPacketsArm}|{self.goodPacketsBody}", file=text_file)
        # else:
            # # print(str(self.number), 'Err:', data, '---', self.msgCount)
            # with open("laptopdata.txt", "a") as text_file:
                    # print(f"{flag}: {data} | {self.msgCount}", file=text_file)
        if time() - self.pastTime >= 5:
            tt = time() - self.pastTime
            print(f"---{self.number}: {tt}s have passed ---")
            with open(f"laptopdata{self.number}.txt", "a") as text_file:
                print('\n***--- 5s have passed ---***\n', file=text_file)
            self.pastTime = time()
            self.msgCount = self.goodPacketCount = self.goodPacketsArm = self.goodPacketsBody = 0

class ConnectionHandlerThread (threading.Thread):
    def __init__(self, connection_index):
        threading.Thread.__init__(self)
        self.connection_index = connection_index
        self.delay = 1 + uniform(0.1, 0.5) #Random delay
        self.isConnected = True
        self.addr = ''

    def reconnect(self, addr):
        while True: #Loop here until reconnected (Thread is doing nothing anyways...)
            try:
                print("reconnecting to ", addr)
                #beetle.connect(beetle.addr)
                p = Peripheral(addr)
                
                #overhead code
                self.connection = p
                self.connection.withDelegate(NotificationDelegate(self.connection_index))
                self.s = self.connection.getServiceByUUID(BLE_SERVICE_UUID)
                self.c = self.s.getCharacteristics()[0]
                
                connections[self.connection_index] = self.connection
                
                print("reconnect-ed to ", addr)
                self.c.write(("H").encode())
                
                self.isConnected = True
                return True
            except:
                print("Error when reconnecting..")
            sleep(self.delay)
            
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
                    self.connection.disconnect()
            #Whenever state of BLE device is disconnected, run this...
            if not self.isConnected:
                print('Trying to reconnect', self.connection_index)
                if self.reconnect(self.addr):
                    print('Successfully reconnected!')
                sleep(self.delay)


## Try connecting to BLEs
def run():
    devices = scanner.scan(2)
    for d in devices:
        if d.addr in bt_addrs:
            addr = d.addr
            idx = bt_addrs[addr]
            print(addr, 'found!')
            try:
                p = Peripheral(addr)
                #connections.append(p)
                connections[idx] = p
                t = ConnectionHandlerThread(idx)
                t.daemon = True #set to true so that can CTRL-C easily
                t.start()
                connection_threads[idx] = t
            except Exception: #Raised when unable to create connection
                print('Error in connecting device')


run()
print('End of initial scan')
    
try:
    while True:
        #run()
        pass
except KeyboardInterrupt:
    print('END OF PROGRAM. Disconnecting all devices..')
    endFlag = True