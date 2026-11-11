/*
 * I2C 地址扫描器（DeskMate 硬件排查用）
 *
 * 用途：
 *   扫描 I2C 总线上所有能响应的设备，并打印它们的 7 位地址。
 *   可以确认 OLED、三轴加速度计、BMP280 的真实地址。
 *
 * 使用方法：
 *   1. 用 Arduino IDE 打开本文件；
 *   2. 选择正确的开发板与串口，点击“上传”；
 *   3. 打开串口监视器，波特率选择 115200；
 *   4. 每 2 秒扫描一次，把打印结果发给排查人员即可。
 *
 * 常见地址对照：
 *   OLED 128x64  -> 0x3C 或 0x3D
 *   LIS3DHTR     -> 0x19 或 0x18
 *   BMP280       -> 0x76 或 0x77
 */

#include <Wire.h>

void setup() {
  Serial.begin(115200);
  Wire.begin();

  Serial.println();
  Serial.println("DeskMate I2C Scanner");
  Serial.println("Scanning every 2 seconds...");
}

void loop() {
  Serial.println();
  Serial.println("--- Scan start ---");

  byte error = 0;
  byte address = 0;
  int found = 0;

  // I2C 7 位地址有效范围：0x01 ~ 0x7F，这里从 1 扫到 126
  for (address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    error = Wire.endTransmission();

    if (error == 0) {
      found++;
      Serial.print("Found 0x");
      if (address < 16) {
        Serial.print("0");
      }
      Serial.print(address, HEX);

      // 标注常见器件，方便一眼看出是谁
      if (address == 0x3C || address == 0x3D) {
        Serial.print("  (OLED)");
      }
      if (address == 0x19 || address == 0x18) {
        Serial.print("  (LIS3DHTR accelerometer)");
      }
      if (address == 0x76 || address == 0x77) {
        Serial.print("  (BMP280 pressure)");
      }
      Serial.println();
    }
  }

  if (found == 0) {
    Serial.println("No I2C device found. Check wiring / power.");
  } else {
    Serial.print("Total devices: ");
    Serial.println(found);
  }

  delay(2000);
}
