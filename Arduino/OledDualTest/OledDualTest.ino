/*
 * OLED 双驱动测试（DeskMate 排查用）
 *
 * 依次尝试 SSD1306 与 SH1106 两种常见驱动初始化 OLED：
 *   1. 前 3 秒尝试 SSD1306，显示 "SSD1306 test"；
 *   2. 后 3 秒尝试 SH1106，显示 "SH1106 test"；
 *   3. 之后保持最后一种显示。
 *
 * 如果其中某一个能正常显示文字，说明 OLED 驱动芯片是那一种，
 * 修改主程序使用对应构造函数即可。
 * 如果两种都仍是白色条形码状白条，则基本可判断为屏幕硬件/供电问题。
 */

#include <Wire.h>
#include <U8x8lib.h>

U8X8_SSD1306_128X64_NONAME_HW_I2C oledSSD(/* reset=*/ U8X8_PIN_NONE);
U8X8_SH1106_128X64_NONAME_HW_I2C oledSH1106(/* reset=*/ U8X8_PIN_NONE);

void setup() {
  Wire.begin();

  // 第一段：SSD1306 驱动
  oledSSD.begin();
  oledSSD.setPowerSave(0);
  oledSSD.clear();
  oledSSD.setFont(u8x8_font_chroma48medium8_r);
  oledSSD.drawString(0, 0, "SSD1306 test");
  oledSSD.drawString(0, 2, "OLED Test OK");
  delay(3000);

  // 第二段：SH1106 驱动
  oledSH1106.begin();
  oledSH1106.setPowerSave(0);
  oledSH1106.clear();
  oledSH1106.setFont(u8x8_font_chroma48medium8_r);
  oledSH1106.drawString(0, 0, "SH1106 test");
  oledSH1106.drawString(0, 2, "OLED Test OK");
  delay(3000);
}

void loop() {
  delay(1000);
}
