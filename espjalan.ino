#define BUZZER 2

bool aiDetect = false;

void setup() {
  Serial.begin(115200);

  pinMode(BUZZER, OUTPUT);
  digitalWrite(BUZZER, LOW);

  Serial.println("ESP32 READY");
}

void loop() {
  // ======================
  // TERIMA DATA DARI PYTHON
  // ======================
  if (Serial.available()) {
    char data = Serial.read();

    Serial.print("DATA DARI PYTHON: ");
    Serial.println(data);

    if (data == '1') {
      aiDetect = true;
    } 
    else if (data == '0') {
      aiDetect = false;
    }
  }

  // ======================
  // KONTROL BUZZER
  // ======================
  if (aiDetect == true) {
    digitalWrite(BUZZER, HIGH);
    Serial.println("STATUS: BAHAYA - BUZZER ON");
  } 
  else {
    digitalWrite(BUZZER, LOW);
    Serial.println("STATUS: AMAN - BUZZER OFF");
  }

  delay(100);
}