/*
 * 加速度计诊断（DeskMate 排查用）
 *
 * 用途：初始化 LIS3DHTR 并连续打印三轴加速度，观察静止时读数是否稳定，
 *       判断敲击检测是否因传感器噪声而误触发。
 *
 * 串口波特率：115200
 */

#include <Wire.h>

uint8_t accelAddr = 0x19;

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
  i2cWriteReg(accelAddr, 0x20, 0x57);   // 100Hz、正常模式、三轴使能
  i2cWriteReg(accelAddr, 0x23, 0x18);   // ±4g、高分辨率
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

void setup() {
  Serial.begin(115200);
  Wire.begin();
  if (!initAccel()) {
    Serial.println("Accel init FAILED");
    while (1) delay(1000);
  }
  Serial.println("ax,ay,az (g), delta_z");
}

void loop() {
  float ax, ay, az;
  static float prevAz = 0;
  readAccel(ax, ay, az);
  Serial.print(ax, 3);
  Serial.print(",");
  Serial.print(ay, 3);
  Serial.print(",");
  Serial.print(az, 3);
  Serial.print(",");
  Serial.println(az - prevAz, 3);
  prevAz = az;
  delay(50);   // 20Hz，静止观察 5 秒左右足够
}
