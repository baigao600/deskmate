/*
 * OLED 最简测试（DeskMate 排查用）
 *
 * 用途：只初始化 OLED 并显示固定文字，排除主程序其它模块的干扰。
 *
 * 如果上传后屏幕能正常显示 "Hello DeskMate"，说明 OLED 本身和接线没问题，
 * 问题出在主程序；如果仍然是一条白色条形码状白条，则多半是屏幕硬件或供电。
 */

#include <Wire.h>
#include <U8x8lib.h>

U8X8_SSD1306_128X64_NONAME_HW_I2C u8x8(/* reset=*/ U8X8_PIN_NONE);

void setup() {
  Wire.begin();
  u8x8.begin();
  u8x8.setPowerSave(0);
  u8x8.setFont(u8x8_font_chroma48medium8_r);
  u8x8.clear();
  u8x8.drawString(0, 0, "Hello DeskMate");
  u8x8.drawString(0, 2, "OLED Test OK");
}

void loop() {
  // 什么都不做，保持显示
  delay(1000);
}
