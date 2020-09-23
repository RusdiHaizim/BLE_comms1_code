#include <SoftwareSerial.h>

unsigned long previous_time = 0;
unsigned long previous_timeA = 0;
unsigned long previous_timeB = 0;
//unsigned long actual_time = 0;
long count = 0;
volatile bool handshake_flag = false;
char buff[20];

//Dummy values to send
//Actual values range from 0-4095
int arr[6] = {0,1,12,123,1234,4021};

//compress + computeChecksum gives a 1-byte checksum
int compress(int num) {
  if (num < 10) {
      return num;
  }
  return num%10 ^ compress(num/10);
}
int computeChecksum(char *s) {
  int output = 0;
  for (int i = 0; i < strlen(s); i++) {
    output ^= s[i];
  }
  return compress(output);
}

//__Deprecated function to print padded numbers__
void padprint(char *s) {
  int count = 3 - strlen(s);
  while (count--) {
    Serial.print('0');
  }
  for (int i = 0; i < strlen(s); i++) {
    Serial.print(s[i]); 
  }
}

//Function to pad numbers being sad with extra 0s. b: buffer to be padded, s: original numbers
void setPad(char *b, char *s) {
  int padsize = 3 - strlen(s);
  int startIdx = strlen(b);
  for (int i = startIdx; i < startIdx+padsize; i++) {
    b[i] = '0';
  }
  int y = 0;
  startIdx = strlen(b);
  for (int i = startIdx; i < startIdx+strlen(s); i++) {
    b[i] = s[y++];
  }
  
}

void setup() {
  Serial.begin(115200);  //initial the Serial
  randomSeed(analogRead(0));
}

//Task to check handshake with laptop
void checkHandshake() {
  if (!handshake_flag && Serial.available()) {
    if (Serial.read() == 'H') {
      buff[0] = 'A';
      Serial.print(buff);
      handshake_flag = true;
      delay(50);
    }
  }

  
}

//Task to send 1st array of values (from arm sensor) ~15-20Hz
void sendArmData() {
  //Send arm sensor
  if (handshake_flag && (millis() - previous_timeA >= 50UL) ) {
    for (int i = 0; i < 1; i++) {
      buff[0] = 48 + i;
      char temp[3];
      
      for (int j = 0; j < 6; j++) {
        itoa(arr[j], temp, 16);
        setPad(buff, temp); //copies temp onto buff with pads
//        Serial.print(buff);
//        delay(1000);
      }
      
      char c[1];
      itoa(computeChecksum(buff), c, 16);
      buff[19] = c[0];
//      if (random(0, 10) == 9) {
//        buff[19] = 'x';
//      }
      Serial.print(buff);
      memset(buff, 0, 20);
//      delay(25);
    }
    previous_timeA = millis();
  }
}

//Task to send 2nd array of values (from body sensor) ~4-5Hz
void sendBodyData() {
    //Send body sensor
  if (handshake_flag && (millis() - previous_timeB >= 200UL) ) {
//    char buff[20] = {0};
    memset(buff, 0, 20);

    for (int i = 1; i < 2; i++) {
      buff[0] = 48 + i;
      char temp[3];
      
      for (int j = 0; j < 6; j++) {
        itoa(arr[j], temp, 16);
        setPad(buff, temp); //copies temp onto buff with pads
      }
      
      char c[1];
      itoa(computeChecksum(buff), c, 16);
      buff[19] = c[0];
      Serial.print(buff);
      memset(buff, 0, 20);
//      delay(25);
    }
    previous_timeB = millis();
  }
}

void loop() {
//  actual_time = millis();
  checkHandshake();
  sendArmData();
  sendBodyData();
}

//    memset(buff, '-', 20);
//    buff[0] = '<';
//    buff[19] = 0;
//    Serial.print(buff);
//    Serial.print('\0');
//    delay(25);
    
//    Serial.print('<');
//    for (int i = 1; i < 20; i++) {
//      Serial.print('-');
//    }
