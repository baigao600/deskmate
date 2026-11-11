/*
 * 倾斜角度诊断（DeskMate 排查用）
 *
 * 打印原始 roll、校准零点、校准后 roll，用于判断设备默认姿态
 * 是否被误判为持续左倾/右倾。
 *
 * 串口波特率：115200
 */

#include <Wire.h>

uint8_t accelAddr = 0x19;
float tiltOffset = 0.0f;

void i2cWriteReg(uint8_t addr, uint8_t reg, uint8_t val) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  Wire.write(val);
  Wire.endTransmission();
}

void i2cReadRegs(uint8_t addr, uint8_t reg, uint8_t* buf, uint8_t len) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  Wire.endTransmission(false);
  Wire.requestFrom(addr, len);
  uint8_t i = 0;
  while (Wire.available() && i < len) {
    buf[i++] = Wire.read();
  }
}

bool initAccel() {
  uint8_t who = 0;
  i2cReadRegs(accelAddr, 0x0F, &who, 1);
  if (who != 0x33) {
    accelAddr = 0x18;
    i2cReadRegs(accelAddr, 0x0F, &who, 1);
    if (who != 0x33) return false;
  }
  i2cWriteReg(accelAddr, 0x20, 0x57);
  i2cWriteReg(accelAddr, 0x23, 0x18);
  return true;
}

void readAccel(float& ax, float& ay, float& az) {
  uint8_t d[6];
  i2cReadRegs(accelAddr, 0x28, d, 6);
  int16_t x = (int16_t)((uint16_t)d[0] | ((uint16_t)d[1] << 8));
  int16_t y = (int16_t)((uint16_t)d[2] | ((uint16_t)d[3] << 8));
  int16_t z = (int16_t)((uint16_t)d[4] | ((uint16_t)d[5] << 8));
  ax = (float)(x >> 4) / 512.0f;
  ay = (float)(y >> 4) / 512.0f;
  az = (float)(z >> 4) / 512.0f;
}

void calibrateTilt() {
  float sum = 0.0f;
  for (int i = 0; i < 20; i++) {
    float ax, ay, az;
    readAccel(ax, ay, az);
    sum += atan2(ax, az) * 180.0f / PI;
    delay(20);
  }
  tiltOffset = sum / 20.0f;
}

void setup() {
  Serial.begin(115200);
  Wire.begin();
  if (!initAccel()) {
    Serial.println("ACCEL FAIL");
    while (1) delay(1000);
  }
  calibrateTilt();
  Serial.println("ax,az,rawRoll,offset,adjustedRoll");
}

void loop() {
  float ax, ay, az;
  readAccel(ax, ay, az);
  float raw = atan2(ax, az) * 180.0f / PI;
  Serial.print(ax, 3);
  Serial.print(",");
  Serial.print(az, 3);
  Serial.print(",");
  Serial.print(raw, 1);
  Serial.print(",");
  Serial.print(tiltOffset, 1);
  Serial.print(",");
  Serial.println(raw - tiltOffset, 1);
  delay(500);
}
