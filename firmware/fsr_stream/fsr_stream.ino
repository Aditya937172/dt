// Two FSR channels only. Packet: S,<micros>,<GPIO34 ADC>,<GPIO35 ADC>
// GPIO34/35 are ADC1 inputs on ESP-WROOM-32.
constexpr int FSR1_PIN = 34;
constexpr int FSR2_PIN = 35;
constexpr uint32_t SAMPLE_PERIOD_US = 10000; // 100 Hz
uint32_t next_sample_us;

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  analogSetPinAttenuation(FSR1_PIN, ADC_11db);
  analogSetPinAttenuation(FSR2_PIN, ADC_11db);
  next_sample_us = micros() + SAMPLE_PERIOD_US;
}

void loop() {
  const uint32_t now = micros();
  if ((int32_t)(now - next_sample_us) < 0) return;
  const uint32_t stamp = now;
  next_sample_us += SAMPLE_PERIOD_US;
  if ((int32_t)(now - next_sample_us) >= 0) next_sample_us = now + SAMPLE_PERIOD_US;
  const int fsr1 = analogRead(FSR1_PIN);
  const int fsr2 = analogRead(FSR2_PIN);
  Serial.printf("S,%lu,%d,%d\n", (unsigned long)stamp, fsr1, fsr2);
}
