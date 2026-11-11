#include <Wire.h>

#define OLED_ADDR 0x3C

void oledCmd(uint8_t c) {
  Wire.beginTransmission(OLED_ADDR);
  Wire.write(0x00);
  Wire.write(c);
  Wire.endTransmission();
}

void setup() {
  Serial.begin(115200);
  Wire.begin();

  static const uint8_t initSeq[] = {
    0xAE, 0xD5, 0x80, 0xA8, 0x3F, 0xD3, 0x00, 0x40,
    0x8D, 0x14, 0x20, 0x00, 0xA1, 0xC8, 0xDA, 0x12,
    0x81, 0xCF, 0xD9, 0xF1, 0xDB, 0x40, 0xA4, 0xA6, 0xAF
  };
  for (unsigned int i = 0; i < sizeof(initSeq); i++) {
    oledCmd(initSeq[i]);
  }

  // 设置列/页地址，写入棋盘格图案
  oledCmd(0x21); oledCmd(0x00); oledCmd(0x7F); // 列 0~127
  oledCmd(0x22); oledCmd(0x00); oledCmd(0x07); // 页 0~7
  Wire.beginTransmission(OLED_ADDR);
  Wire.write(0x40);
  for (int i = 0; i < 1024; i++) {
    Wire.write((i & 0x01) ? 0xAA : 0x55);
  }
  Wire.endTransmission();

  Serial.println("RAW OLED test pattern written");
}

void loop() {
}
