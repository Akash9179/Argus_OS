// ugv-01 MCU firmware, as supplied by the team on 2026-08-11.
//
// PROVENANCE: handed over by the developer as the source running on the
// vehicle's control board. It has NOT been read back off the chip, so it is
// the source we were given, not verified silicon. It corroborates the wire
// protocol we observed independently (115200, R<n><0|1>, P<42..214>), which
// is strong evidence it is the right sketch.
//
// DO NOT REFLASH THE BOARD WITH THIS without a wheels-up bench session. See
// bodies/ugv-01/MCU-PROTOCOL.md for the analysis and for the watchdog this
// firmware is missing.

const byte relayPins[14] = {
  2,3,4,5,6,7,8,10,11,12,A0,A1,A2,A3
};

const byte pwmPin = 9;

void setup() {

  Serial.begin(115200);

  for(int i=0;i<14;i++){
    pinMode(relayPins[i],OUTPUT);
    digitalWrite(relayPins[i],HIGH); 
  }

  pinMode(pwmPin,OUTPUT);

  TCCR1B = (TCCR1B & 0b11111000) | 0x01;

  analogWrite(pwmPin,42);
}

void loop() {

  if(!Serial.available()) return;

  String cmd = Serial.readStringUntil('\n');
  cmd.trim();

  if(cmd.startsWith("P")){

    int value = cmd.substring(1).toInt();

    value = constrain(value,42,214);

    analogWrite(pwmPin,value);

    return;
  }

  if(cmd.startsWith("R")){

    int len = cmd.length();

    int state = cmd.substring(len-1).toInt();

    int relay = cmd.substring(1,len-1).toInt();

    if(relay>=1 && relay<=14){

      digitalWrite(
        relayPins[relay-1],
        state ? LOW : HIGH
      );

    }

  }

}
