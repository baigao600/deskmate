/*
 * DeskMate Pro - Arduino 端
 * 双模式桌面控制与消息提醒中心（控制模式 / 消息模式）
 *
 * 硬件：Seeed Studio Grove Beginner Kit for Arduino
 *
 * 引脚映射（请按你的实际接线修改下方 #define）：
 *   OLED 128x64   I2C，地址 0x3C（使用 U8x8 纯文本模式）
 *   旋转电位器    A0（模拟输入）
 *   按钮          D2（内部上拉，按下为 LOW）
 *   蜂鸣器        D3（PWM 可调）
 *   LED           D4（默认单色，PWM 可调）
 *                 ——若使用 RGB LED，则占用 D4/D5/D6，
 *                   此时 DHT11 请改接到其它空闲引脚（例如 D7）并同步修改 DHT_PIN
 *   温湿度 DHT11   D5（单总线）
 *   三轴加速度计  I2C，LIS3DHTR，地址 0x19（若为 0x18 会自动回退尝试）
 *   气压 BMP280    I2C，地址 0x76（失败自动尝试 0x77）
 *   光传感器      A1（模拟输入）
 * 通信协议：波特率 115200，每条 JSON 以 '\n' 结尾。
 *
 * 依赖库安装（Arduino IDE：工具 -> 管理库）：
 *   - U8g2                        （by oliver，其中包含 U8x8lib.h）
 *   - DHT sensor library          （by Adafruit）
 *
 * 说明：为适配 ATmega328P 有限的 Flash/RAM，BMP280 与 LIS3DHTR
 *       使用原始 I2C 寄存器读取，未依赖 Adafruit 对应库；OLED 使用
 *       U8x8 纯文本模式代替 U8g2 图形模式。这样仍能完整实现协议与功能。
 */

#include <Wire.h>
#include <U8x8lib.h>
#include <math.h>

// ======================= 引脚与常量定义 =======================
#define POT_PIN         A0      // 旋转电位器（模拟输入）
#define BUTTON_PIN      6       // 按钮（Grove Beginner Kit 默认 D6；模块自带下拉，按下为 HIGH）
#define BUZZER_PIN      3       // 蜂鸣器（PWM）
#define LED_PIN         4       // 单色 LED；若你的板子 D4 不支持 PWM，
                               // 呼吸会退化为“缓慢闪烁”。如需平滑呼吸，
                               // 可把 LED 接到 PWM 脚（如 D6）并同步修改此处。
// RGB LED 可选：如果确实使用 RGB LED（D4=红、D5=绿、D6=蓝），
// 请取消下面这行注释，并把 DHT_PIN 改为其它空闲数字脚（如 D7）。
// 注意：默认保持注释，使用 D4 单色 LED，避免与 DHT11 引脚冲突。
// #define USE_RGB_LED
#ifdef USE_RGB_LED
#define LED_RED_PIN     4
#define LED_GREEN_PIN   5
#define LED_BLUE_PIN    6
#endif

#define OLED_ADDR       0x3C
#define ACCEL_ADDR      0x19    // LIS3DHTR 常见地址（失败会尝试 0x18）

#define SERIAL_BAUD     115200
#define JSON_BUF_LEN    96
#define MAX_MSGS        4

// Arduino 核心通常只定义 PI，这里补充 2*PI，供 LED 呼吸使用
#ifndef TWO_PI
#define TWO_PI (2.0f * PI)
#endif

// 按钮阈值
#define CLICK_MAX_MS        800   // 短按：按下持续时间小于该值
#define LONG_PRESS_MS       2000  // 长按：按下持续时间达到该值
#define MULTI_CLICK_GAP_MS  600   // 双击/三击两次短按之间的最大间隔
#define DEBOUNCE_SAMPLE_MS  10    // 去抖采样周期
#define DEBOUNCE_STABLE_MS  30    // 电平稳定多久才视为有效

// 倾斜 / 敲击参数
#define TILT_ANGLE_DEG      10.0f // 倾斜判定角度
#define TILT_HYST_DEG       2.0f  // 迟滞，防止临界抖动
#define TILT_HOLD_MS        120   // 持续超过该时间才触发
#define TILT_COOLDOWN_MS    500   // 触发后 0.5 秒内不再重复切换
#define KNOCK_THRESHOLD_G   0.20f // 三轴合力偏离 1g 的幅度阈值（≈ 合力达到 1.2g）
#define KNOCK_MAX_MS        50    // 变化持续时间上限
#define KNOCK_COOLDOWN_MS   500   // 触发后 0.5 秒内不再触发

// 临时自测开关：如需验证电脑端截屏/虚拟桌面切换，可取消注释；
// 正式使用时请保持注释，避免占用资源。
// #define SELF_TEST

// 屏幕轮播时间
#define MAIN_SCREEN_MS      5000  // 主界面显示 5 秒
#define ENV_SCREEN_MS       3000  // 环境界面显示 3 秒

// ======================= 全局对象 =======================
U8X8_SSD1306_128X64_NONAME_HW_I2C u8x8(/* reset=*/ U8X8_PIN_NONE);

// ======================= 数据结构 =======================
enum Mode {
  MODE_CONTROL = 0,
  MODE_MESSAGE = 1
};

// ======================= 前向声明（供函数间相互调用） =======================
void sendEvent(const char* json);
void playPattern(const unsigned int* freqs, const unsigned int* durs, int n);
void shortBeep();
void lowBeep();
void startLedFlash(int times);
void switchMode(Mode newMode);
void clearAllMessages();
void removeMessageAt(int index);
void addMessageToList(long id, const char* src, const char* title, const char* time);
void escapeJsonTo(const char* src, char* dst, int dstLen);

// ======================= 全局状态 =======================
Mode currentMode = MODE_CONTROL;
int  volume = 50;                 // 0~100
bool muted = false;               // 静音状态（Arduino 本地记录，用于 LED 显示）

int  msgCount = 0;                // 未读消息数量（当前列表只保存未读）
int  selectedIndex = 0;           // 消息模式旋钮选中的索引
bool dnd = false;                 // 免打扰

struct Msg {
  long id;
  char src[8];
  char title[32];
  char time[6];
};

Msg  messages[MAX_MSGS];

bool  accelOk = false;

// LIS3DHTR 原始 I2C 读取
uint8_t accelAddr = ACCEL_ADDR;

// 屏幕轮播
enum ScreenState { SCREEN_MAIN, SCREEN_ENV };
ScreenState screenState = SCREEN_MAIN;
unsigned long screenStateStart = 0;
int scrollOffset = 0;             // 标题滚动偏移
unsigned long scrollLast = 0;
int  scrollDir = 1;               // 标题滚动方向：1=向右推进，-1=回退

// 按钮去抖与动作检测
// 使用内部上拉。btnReleasedLevel 表示“未按下”时的电平，开机自动校准，
// 以兼容按下为 LOW（普通上拉按钮）或按下为 HIGH（部分 Grove 按钮）两种接法。
bool btnStable = HIGH;
bool btnPrevStable = HIGH;
bool btnPendingRaw = HIGH;
int  btnReleasedLevel = HIGH;       // 释放态电平，setup 中校准
unsigned long btnLastSample = 0;
unsigned long btnPendingSince = 0;

unsigned long pressStart = 0;
bool pressActive = false;
bool longFired = false;
int  pendingClicks = 0;
unsigned long lastShortRelease = 0;

// 旋钮滤波
const int KNOB_WINDOW = 16;
int  knobSamples[KNOB_WINDOW] = {0};
int  knobSampleIdx = 0;
int  knobFiltered = 0;
bool knobInited = false;
unsigned long lastKnobRead = 0;
int  lastKnobMsgVal = -1;   // 消息模式增量浏览：上一次旋钮位置

// 倾斜检测
float filtAx = 0, filtAy = 0, filtAz = 1.0f;
int   tiltState = 0;              // -1=后倾, 0=水平, 1=前倾
unsigned long tiltStateStart = 0;
unsigned long lastTiltSend = 0;
unsigned long lastTiltEnd = 0;    // 倾斜回正的时刻，用于回正后短暂继续屏蔽敲击
unsigned long lastAccelRead = 0;
float tiltOffset = 0.0f;          // 开机自校准的倾斜零点（度）

// 敲击检测
unsigned long lastKnockSend = 0;
bool  knockCandidate = false;
unsigned long knockCandidateStart = 0;
int   knockAboveCount = 0;        // 连续超过阈值的采样次数

// 蜂鸣器非阻塞音符队列
#define BUZZER_MAX_NOTES 8
unsigned int  buzzerFreqs[BUZZER_MAX_NOTES];
unsigned int  buzzerDurs[BUZZER_MAX_NOTES];
int  buzzerCount = 0;
int  buzzerIdx = 0;
bool buzzerBusy = false;
unsigned long buzzerNoteStart = 0;

// LED 非阻塞呼吸/闪烁
unsigned long lastLedUpdate = 0;
float breathPhase = 0.0f;
bool  ledFlashActive = false;
int   ledFlashCount = 0;
bool  ledFlashOn = false;
unsigned long ledFlashLast = 0;

// 串口接收缓冲区（按行拼装）
char serialLineBuffer[JSON_BUF_LEN + 1];
int  serialLineLen = 0;

// ======================= I2C 原始驱动（减少库依赖，缩小代码体积） =======================
// 写单字节寄存器
void i2cWriteReg(uint8_t addr, uint8_t reg, uint8_t val) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  Wire.write(val);
  Wire.endTransmission();
}

// 连续读寄存器
void i2cReadRegs(uint8_t addr, uint8_t reg, uint8_t* buf, uint8_t len) {
  Wire.beginTransmission(addr);
  Wire.write(reg | 0x80);   // bit7: I2C 连续读（地址自动递增）
  Wire.endTransmission(false);
  Wire.requestFrom(addr, len);
  uint8_t i = 0;
  while (Wire.available() && i < len) {
    buf[i++] = Wire.read();
  }
}

// 初始化 LIS3DHTR，成功返回 true
bool initAccel() {
  uint8_t who = 0;
  i2cReadRegs(ACCEL_ADDR, 0x0F, &who, 1);
  if (who == 0x33) {
    accelAddr = ACCEL_ADDR;
  } else {
    i2cReadRegs(0x18, 0x0F, &who, 1);
    if (who == 0x33) accelAddr = 0x18;
    else return false;
  }
  // 100Hz、正常模式、三轴使能
  i2cWriteReg(accelAddr, 0x20, 0x57);
  // ±2g、高分辨率（12bit，左对齐）
  // 0x88 = BDU(0x80) + FS=±2g(0x00) + 高分辨率 HR(0x08)
  i2cWriteReg(accelAddr, 0x23, 0x88);
  return true;
}

// 读取 LIS3DHTR 三轴加速度（单位 g）
void readAccel(float& ax, float& ay, float& az) {
  uint8_t d[6];
  i2cReadRegs(accelAddr, 0x28, d, 6);
  int16_t x = (int16_t)((uint16_t)d[0] | ((uint16_t)d[1] << 8));
  int16_t y = (int16_t)((uint16_t)d[2] | ((uint16_t)d[3] << 8));
  int16_t z = (int16_t)((uint16_t)d[4] | ((uint16_t)d[5] << 8));
  // 12bit 左对齐：右移 4 位；±2g 满量程对应 2048，/1024 得到 g
  ax = (float)(x >> 4) / 1024.0f;
  ay = (float)(y >> 4) / 1024.0f;
  az = (float)(z >> 4) / 1024.0f;
}

// 开机自校准：读取当前姿态的平均角度作为倾斜零点。
// 设备静止时即使不是水平放置，也不会被误判成持续倾斜。
void calibrateTilt() {
  float sum = 0.0f;
  int samples = 20;
  for (int i = 0; i < samples; i++) {
    float ax, ay, az;
    readAccel(ax, ay, az);
    sum += atan2(ay, az) * 180.0f / PI;
    delay(20);
  }
  tiltOffset = sum / (float)samples;
  tiltState = 0;
  tiltStateStart = 0;
  lastTiltSend = 0;
}

// ======================= 辅助函数：串口 JSON =======================
// 发送一条 JSON 事件，自动补 '\n'
void sendEvent(const char* json) {
  Serial.print(json);
  Serial.print('\n');
}

// 从 JSON 中提取字符串值（原地截断，返回指向值的指针，不额外分配堆内存）
const char* extractJsonString(char* json, const char* key) {
  char needle[24];
  snprintf(needle, sizeof(needle), "\"%s\"", key);
  char* p = strstr(json, needle);
  if (!p) return "";
  p = strchr(p + strlen(needle), ':');
  if (!p) return "";
  p++;
  while (*p == ' ' || *p == '\t' || *p == '\r') p++;
  if (*p != '"') return "";
  p++;
  char* end = strchr(p, '"');
  if (!end) return "";
  *end = '\0';
  return p;
}

// 从 JSON 中提取长整型值
long extractJsonLong(const char* json, const char* key, long def = 0) {
  char needle[24];
  snprintf(needle, sizeof(needle), "\"%s\"", key);
  const char* p = strstr(json, needle);
  if (!p) return def;
  p = strchr(p + strlen(needle), ':');
  if (!p) return def;
  p++;
  while (*p == ' ' || *p == '\t' || *p == '\r') p++;
  return atol(p);
}

// 把一条消息加入未读列表（不负责声音/灯光提示，供 new_msg 与 load_msg 复用）
void addMessageToList(long id, const char* src, const char* title, const char* time) {
  Msg* m;
  if (msgCount < MAX_MSGS) {
    m = &messages[msgCount];
    msgCount++;
  } else {
    // 列表已满：丢弃最旧一条，新消息加入末尾
    for (int i = 0; i < MAX_MSGS - 1; i++) messages[i] = messages[i + 1];
    m = &messages[MAX_MSGS - 1];
  }
  m->id = id;
  strncpy(m->src, src, sizeof(m->src) - 1); m->src[sizeof(m->src) - 1] = '\0';
  strncpy(m->title, title, sizeof(m->title) - 1); m->title[sizeof(m->title) - 1] = '\0';
  strncpy(m->time, time, sizeof(m->time) - 1); m->time[sizeof(m->time) - 1] = '\0';
  if (selectedIndex >= msgCount) selectedIndex = msgCount - 1;
  if (selectedIndex < 0) selectedIndex = 0;
}

// 处理电脑端发来的单条 JSON 指令
void handleCommand(char* json) {
  if (!strstr(json, "\"cmd\"")) return;

  if (strstr(json, "\"set_mode\"")) {
    const char* mode = extractJsonString(json, "mode");
    if (strcmp(mode, "message") == 0 && currentMode != MODE_MESSAGE) switchMode(MODE_MESSAGE);
    else if (strcmp(mode, "control") == 0 && currentMode != MODE_CONTROL) switchMode(MODE_CONTROL);
  }
  else if (strstr(json, "\"new_msg\"") || strstr(json, "\"load_msg\"")) {
    bool isNew = strstr(json, "\"new_msg\"") != NULL;
    long id = extractJsonLong(json, "id", -1);
    if (id < 0) id = millis();
    const char* time = extractJsonString(json, "time");
    const char* title = extractJsonString(json, "title");
    const char* src = extractJsonString(json, "src");
    addMessageToList(id, src, title, time);

    if (isNew) {
      // 新消息声音与灯光提示：邮件两短音；其它短促提示
      if (strcmp(src, "calendar") == 0) {
        unsigned int cal[6] = {2000, 0, 2000, 0, 2000, 0};
        unsigned int cdu[6] = {70, 50, 70, 50, 70, 50};
        playPattern(cal, cdu, 6);
      } else {
        unsigned int em[4] = {1800, 0, 1800, 0};
        unsigned int edu[4] = {80, 60, 80, 60};
        playPattern(em, edu, 4);
      }
      startLedFlash(3);
    }
  }
  else if (strstr(json, "\"sync_volume\"")) {
    int v = (int)extractJsonLong(json, "val", volume);
    if (v < 0) v = 0;
    if (v > 100) v = 100;
    volume = v;
  }
#ifdef SELF_TEST
  else if (strstr(json, "\"selftest\"")) {
    for (int i = 0; i < 5; i++) {
      sendEvent("{\"evt\":\"knock\"}");
      delay(200);
      sendEvent("{\"evt\":\"tilt\",\"dir\":\"right\"}");
      delay(200);
    }
  }
#endif
  else if (strstr(json, "\"clear_msgs\"")) {
    clearAllMessages();
  }
}

// ======================= 按钮状态机 =======================
// 开机校准按钮“释放态”电平，兼容按下为 LOW 或 HIGH 两种接法。
void calibrateButton() {
  int level = digitalRead(BUTTON_PIN);
  // 连续采样几次取众数，避免上电瞬间抖动
  int countHigh = 0, countLow = 0;
  for (int i = 0; i < 12; i++) {
    delay(10);
    if (digitalRead(BUTTON_PIN) == HIGH) countHigh++;
    else countLow++;
  }
  level = (countHigh >= countLow) ? HIGH : LOW;
  btnReleasedLevel = level;
  btnStable = level;
  btnPrevStable = level;
  btnPendingRaw = level;
}

void sampleButton() {
  unsigned long now = millis();
  if (now - btnLastSample < DEBOUNCE_SAMPLE_MS) return;
  btnLastSample = now;

  bool raw = digitalRead(BUTTON_PIN);
  // 防抖：电平变化后不立即采信，而是等待稳定 DEBOUNCE_STABLE_MS 再确认
  if (raw != btnPendingRaw) {
    btnPendingRaw = raw;
    btnPendingSince = now;
  }
  if (now - btnPendingSince < DEBOUNCE_STABLE_MS) return;
  if (btnPendingRaw == btnStable) return;   // 电平没有真正改变
  btnStable = btnPendingRaw;

  bool stableNow = btnStable;
  if (stableNow == btnPrevStable) return;
  btnPrevStable = stableNow;

  if (stableNow != btnReleasedLevel) {
    // 按下沿
    pressActive = true;
    longFired = false;
    pressStart = now;
  } else {
    // 释放沿
    pressActive = false;
    unsigned long duration = now - pressStart;
    if (!longFired && duration < CLICK_MAX_MS) {
      pendingClicks++;
      lastShortRelease = now;
    }
  }
}

void resolvePendingClicks() {
  if (pendingClicks == 0) return;
  unsigned long now = millis();
  if (now - lastShortRelease < MULTI_CLICK_GAP_MS) return;

  int clicks = pendingClicks;
  pendingClicks = 0;

  if (clicks >= 3) {
    // 三击：切换模式
    Mode next = (currentMode == MODE_CONTROL) ? MODE_MESSAGE : MODE_CONTROL;
    switchMode(next);
  } else if (clicks == 2) {
    // 双击
    if (currentMode == MODE_CONTROL) {
      sendEvent("{\"evt\":\"btn\",\"act\":\"double\"}");
    } else {
      // 消息模式：清除所有未读
      clearAllMessages();
      sendEvent("{\"evt\":\"btn\",\"act\":\"double\"}");
    }
  } else if (clicks == 1) {
    // 单击
    if (currentMode == MODE_CONTROL) {
      sendEvent("{\"evt\":\"btn\",\"act\":\"single\"}");
      shortBeep();
    } else {
      // 消息模式：打开当前消息
      if (msgCount > 0 && selectedIndex >= 0 && selectedIndex < msgCount) {
        char esrc[16], etitle[64];
        escapeJsonTo(messages[selectedIndex].src, esrc, sizeof(esrc));
        escapeJsonTo(messages[selectedIndex].title, etitle, sizeof(etitle));
        char buf[128];   // 足够容纳转义后的 src/title 与 id（超长由 snprintf 兜底截断）
        snprintf(buf, sizeof(buf),
                 "{\"evt\":\"msg_open\",\"id\":%ld,\"src\":\"%s\",\"title\":\"%s\"}",
                 messages[selectedIndex].id, esrc, etitle);
        sendEvent(buf);
        removeMessageAt(selectedIndex);
        if (selectedIndex >= msgCount) selectedIndex = msgCount - 1;
        if (selectedIndex < 0) selectedIndex = 0;
      }
      shortBeep();
    }
  }
}

void checkLongPress() {
  if (!pressActive || longFired) return;
  unsigned long now = millis();
  if (now - pressStart >= LONG_PRESS_MS) {
    longFired = true;
    if (currentMode == MODE_CONTROL) {
      muted = !muted;   // 本地同步静音，用于 LED 显示
      sendEvent("{\"evt\":\"btn\",\"act\":\"long\"}");
    } else {
      dnd = !dnd;       // 切换免打扰
      sendEvent("{\"evt\":\"btn\",\"act\":\"long\"}");
    }
    lowBeep();
  }
}

// ======================= 旋钮 =======================
int readKnob() {
  int raw = analogRead(POT_PIN);
  if (!knobInited) {
    for (int i = 0; i < KNOB_WINDOW; i++) knobSamples[i] = raw;
    knobSampleIdx = 0;
    knobFiltered = raw;
    knobInited = true;
  } else {
    knobSamples[knobSampleIdx] = raw;
    knobSampleIdx = (knobSampleIdx + 1) % KNOB_WINDOW;
    long sum = 0;
    for (int i = 0; i < KNOB_WINDOW; i++) sum += knobSamples[i];
    knobFiltered = (int)(sum / KNOB_WINDOW);
  }
  return knobFiltered;
}

void processKnob() {
  unsigned long now = millis();
  if (now - lastKnobRead < 40) return;   // 约 25Hz，减少抖动与串口流量
  lastKnobRead = now;

  int raw = readKnob();
  int val = map(raw, 0, 1023, 0, 100);
  if (val < 0) val = 0;
  if (val > 100) val = 100;

  if (currentMode == MODE_CONTROL) {
    if (abs(val - volume) > 2) {
      volume = val;
      char buf[40];
      snprintf(buf, sizeof(buf), "{\"evt\":\"volume\",\"val\":%d}", volume);
      sendEvent(buf);
    }
  } else {
    // 消息模式：旋钮浏览未读消息列表（绝对位置映射）
    int idx = 0;
    if (msgCount > 1) {
      idx = map(val, 0, 100, 0, msgCount - 1);
      if (idx < 0) idx = 0;
      if (idx >= msgCount) idx = msgCount - 1;
    }
    if (idx != selectedIndex) {
      selectedIndex = idx;
      char buf[40];
      snprintf(buf, sizeof(buf), "{\"evt\":\"msg_select\",\"index\":%d}", selectedIndex);
      sendEvent(buf);
    }
  }
}

// ======================= 加速度计：倾斜 + 敲击 =======================
void processAccel() {
  unsigned long now = millis();
  if (now - lastAccelRead < 20) return;   // 50Hz，提高敲击检测灵敏度
  lastAccelRead = now;
  if (!accelOk) return;

  float ax, ay, az;
  readAccel(ax, ay, az);

  // 低通滤波（指数移动平均）
  const float alpha = 0.20f;
  filtAx = alpha * ax + (1.0f - alpha) * filtAx;
  filtAy = alpha * ay + (1.0f - alpha) * filtAy;
  filtAz = alpha * az + (1.0f - alpha) * filtAz;

  // 前后倾斜：绕 X 轴旋转（前倾为正，后倾为负）
  // 减去开机自校准的零点，避免设备默认摆放姿态被当成持续倾斜
  float roll = atan2(filtAy, filtAz) * 180.0f / PI - tiltOffset;

  int newState = 0;
  if (roll < -TILT_ANGLE_DEG) newState = -1;
  else if (roll > TILT_ANGLE_DEG) newState = 1;

  // 迟滞：离开判定区间需要回退 TILT_HYST_DEG
  if (tiltState == -1 && roll > -(TILT_ANGLE_DEG - TILT_HYST_DEG)) newState = 0;
  if (tiltState == 1  && roll < (TILT_ANGLE_DEG - TILT_HYST_DEG)) newState = 0;

  if (newState != tiltState) {
    if (newState == 0 && tiltState != 0) {
      lastTiltEnd = now;   // 倾斜回正，记录时刻，用于回正后短暂继续屏蔽敲击
    }
    tiltState = newState;
    tiltStateStart = now;
  }

  if (tiltState != 0 && (now - tiltStateStart >= TILT_HOLD_MS) &&
      (now - lastTiltSend >= TILT_COOLDOWN_MS)) {
    lastTiltSend = now;
    if (tiltState == -1) sendEvent("{\"evt\":\"tilt\",\"dir\":\"left\"}");
    else sendEvent("{\"evt\":\"tilt\",\"dir\":\"right\"}");
  }

  // 敲击检测：三轴合成加速度偏离 1g 的幅度。
  // 倾斜只会改变重力方向，合力始终约 1g，因此不会误触发；
  // 敲击会在短时间内给传感器叠加额外加速度，使合力明显偏离 1g。
  //
  // 检测到明显倾斜时屏蔽敲击，避免倾斜切换桌面时的晃动被误判成截图。
  // 倾斜回正后额外再屏蔽 500ms，避免连续倾斜经过水平位置时误触发。
  if (tiltState != 0 || (now - lastTiltEnd < 500)) {
    knockAboveCount = 0;
    knockCandidate = false;
  } else {
    float mag = sqrt(ax * ax + ay * ay + az * az);
    float deviation = fabs(mag - 1.0f);

    if (deviation > KNOCK_THRESHOLD_G) {
      knockAboveCount++;
      // 单次采样超过阈值即认为可能是一次敲击，提高灵敏度
      if (knockAboveCount >= 1 && !knockCandidate) {
        knockCandidate = true;
        knockCandidateStart = now;
      }
    } else {
      knockAboveCount = 0;
      if (knockCandidate) {
        if ((now - knockCandidateStart <= KNOCK_MAX_MS) &&
            (now - lastKnockSend >= KNOCK_COOLDOWN_MS)) {
          lastKnockSend = now;
          sendEvent("{\"evt\":\"knock\"}");
        }
        knockCandidate = false;
      }
    }

    if (knockCandidate && (now - knockCandidateStart > KNOCK_MAX_MS)) {
      knockCandidate = false;
      knockAboveCount = 0;
    }
  }
}

// ======================= OLED 显示 =======================
// 使用 U8x8 纯文本模式，占用极少的 Flash 和 RAM，适合 ATmega328P。
// 每行 16 个字符（默认 8x8 字体），共 8 行。

// 超长标题按字符滚动显示（最多显示 16 个字符）。
void drawScrolledText(const char* text, uint8_t row) {
  int len = (int)strlen(text);
  if (len <= 16) {
    u8x8.drawString(0, row, text);
    return;
  }

  unsigned long now = millis();
  if (now - scrollLast >= 250) {
    scrollLast = now;
    int range = len - 16;
    scrollOffset += scrollDir;
    if (scrollOffset >= range) {
      scrollOffset = range;
      scrollDir = -1;
    } else if (scrollOffset <= 0) {
      scrollOffset = 0;
      scrollDir = 1;
    }
  }

  char buf[17];
  int n = 0;
  for (int i = scrollOffset; i < len && n < 16; i++) {
    buf[n++] = text[i];
  }
  buf[n] = '\0';
  u8x8.drawString(0, row, buf);
}

void drawControlScreen() {
  u8x8.clearDisplay();
  u8x8.drawString(0, 0, "Control Mode");
  char volBuf[16];
  snprintf(volBuf, sizeof(volBuf), "Volume: %d%%", volume);
  u8x8.drawString(0, 1, volBuf);
  u8x8.drawString(0, 2, muted ? "Muted" : "Play");
  u8x8.drawString(0, 4, "Tilt=Desktop");
  u8x8.drawString(0, 5, "Knock=Shot");
}

void drawMessageScreen() {
  u8x8.clearDisplay();
  char countBuf[16];
  snprintf(countBuf, sizeof(countBuf), "%d Unread", msgCount);
  u8x8.drawString(0, 0, countBuf);

  if (msgCount > 0) {
    if (selectedIndex < 0) selectedIndex = 0;
    if (selectedIndex >= msgCount) selectedIndex = msgCount - 1;
    Msg& m = messages[selectedIndex];
    u8x8.drawString(0, 1, m.src);
    u8x8.drawString(0, 2, m.time);
    drawScrolledText(m.title, 4);
  } else {
    u8x8.drawString(0, 2, "No messages");
  }
  u8x8.drawString(0, 6, "Rot=Browse Clk=Open");
}

void updateScreen() {
  unsigned long now = millis();
  bool needDraw = false;

  // 只有显示内容变化时才重绘，避免静态画面被反复清屏重写导致闪烁
  static int prevMode = -1;
  static int prevVolume = -1;
  static int prevMuted = -1;
  static int prevMsgCount = -1;
  static int prevSelected = -1;

  if (currentMode != prevMode ||
      volume != prevVolume ||
      muted != prevMuted ||
      msgCount != prevMsgCount ||
      selectedIndex != prevSelected) {
    needDraw = true;
  }

  // 消息模式长标题需要持续滚动：每 250ms 重绘一次
  static unsigned long lastScrollDraw = 0;
  if (currentMode == MODE_MESSAGE && msgCount > 0 &&
      (now - lastScrollDraw >= 250)) {
    needDraw = true;
  }

  if (!needDraw) return;

  // 保存本次快照
  prevMode = (int)currentMode;
  prevVolume = volume;
  prevMuted = muted ? 1 : 0;
  prevMsgCount = msgCount;
  prevSelected = selectedIndex;
  lastScrollDraw = now;

  if (currentMode == MODE_CONTROL) drawControlScreen();
  else drawMessageScreen();
}

// ======================= 蜂鸣器 =======================
void playPattern(const unsigned int* freqs, const unsigned int* durs, int n) {
  if (n <= 0) return;
  if (n > BUZZER_MAX_NOTES) n = BUZZER_MAX_NOTES;
  for (int i = 0; i < n; i++) {
    buzzerFreqs[i] = freqs[i];
    buzzerDurs[i] = durs[i];
  }
  buzzerCount = n;
  buzzerIdx = 0;
  buzzerBusy = true;
  buzzerNoteStart = millis();
  if (buzzerFreqs[0] > 0) tone(BUZZER_PIN, buzzerFreqs[0]);
  else noTone(BUZZER_PIN);
}

void shortBeep() {
  unsigned int f[1] = {1800};
  unsigned int d[1] = {50};
  playPattern(f, d, 1);
}

void lowBeep() {
  unsigned int f[1] = {600};
  unsigned int d[1] = {120};
  playPattern(f, d, 1);
}

void updateBuzzer() {
  if (!buzzerBusy) return;
  unsigned long now = millis();
  if (now - buzzerNoteStart < buzzerDurs[buzzerIdx]) return;

  buzzerIdx++;
  if (buzzerIdx >= buzzerCount) {
    noTone(BUZZER_PIN);
    buzzerBusy = false;
    return;
  }
  buzzerNoteStart = now;
  if (buzzerFreqs[buzzerIdx] > 0) tone(BUZZER_PIN, buzzerFreqs[buzzerIdx]);
  else noTone(BUZZER_PIN);
}

// ======================= LED =======================
void setLedRaw(int brightness) {
#ifdef USE_RGB_LED
  analogWrite(LED_RED_PIN, brightness);
  analogWrite(LED_GREEN_PIN, brightness);
  analogWrite(LED_BLUE_PIN, brightness);
#else
  analogWrite(LED_PIN, brightness);
#endif
}

void startLedFlash(int times) {
  ledFlashActive = true;
  ledFlashCount = times;
  ledFlashOn = false;
  ledFlashLast = millis();
}

void updateLed() {
  unsigned long now = millis();
  if (now - lastLedUpdate < 30) return;
  lastLedUpdate = now;

  if (ledFlashActive) {
    if (now - ledFlashLast >= 120) {
      ledFlashLast = now;
      ledFlashOn = !ledFlashOn;
      if (ledFlashOn) ledFlashCount--;
      if (ledFlashCount <= 0) {
        ledFlashActive = false;
        setLedRaw(0);
        return;
      }
    }
    setLedRaw(ledFlashOn ? 255 : 0);
    return;
  }

  bool breathe = false;
  bool solidOn = false;
  if (currentMode == MODE_CONTROL) {
    if (muted) solidOn = true;
    else breathe = true;
  } else {
    if (dnd) solidOn = true;
    else if (msgCount > 0) breathe = true;
  }

  if (solidOn) {
    setLedRaw(255);
  } else if (breathe) {
    breathPhase += 0.12f;
    if (breathPhase > TWO_PI) breathPhase -= TWO_PI;
    int b = (int)((sin(breathPhase) + 1.0f) * 127.5f);
    setLedRaw(b);
  } else {
    setLedRaw(0);
  }
}

// ======================= 模式切换与消息管理 =======================
void escapeJsonTo(const char* src, char* dst, int dstLen) {
  int j = 0;
  for (int i = 0; src[i] && j < dstLen - 3; i++) {
    char c = src[i];
    if (c == '"' || c == '\\') {
      dst[j++] = '\\';
      dst[j++] = c;
    } else if (c == '\n') {
      dst[j++] = '\\';
      dst[j++] = 'n';
    } else if (c == '\r') {
      dst[j++] = '\\';
      dst[j++] = 'r';
    } else {
      dst[j++] = c;
    }
  }
  dst[j] = '\0';
}

void clearAllMessages() {
  msgCount = 0;
  selectedIndex = 0;
  // 清除提示音与 LED 熄灭
  unsigned int f[1] = {900};
  unsigned int d[1] = {300};
  playPattern(f, d, 1);
  ledFlashActive = false;
}

void removeMessageAt(int index) {
  if (index < 0 || index >= msgCount) return;
  for (int i = index; i < msgCount - 1; i++) messages[i] = messages[i + 1];
  msgCount--;
}

void switchMode(Mode newMode) {
  if (currentMode == newMode) return;
  currentMode = newMode;
  selectedIndex = 0;
  lastKnobMsgVal = -1;
  scrollOffset = 0;
  scrollDir = 1;
  screenState = SCREEN_MAIN;      // 立即显示新模式的名称/界面
  screenStateStart = millis();

  char buf[48];
  snprintf(buf, sizeof(buf), "{\"evt\":\"mode\",\"mode\":\"%s\"}",
           currentMode == MODE_CONTROL ? "control" : "message");
  sendEvent(buf);
}

// ======================= 串口接收 =======================
void readSerialCommands() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      serialLineBuffer[serialLineLen] = '\0';
      if (serialLineLen > 0) handleCommand(serialLineBuffer);
      serialLineLen = 0;
    } else if (c != '\r') {
      if (serialLineLen < JSON_BUF_LEN) serialLineBuffer[serialLineLen++] = c;
    }
  }
}

// ======================= setup / loop =======================
void setup() {
  Serial.begin(SERIAL_BAUD);

  pinMode(BUTTON_PIN, INPUT_PULLUP);
  calibrateButton();
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
#ifdef USE_RGB_LED
  pinMode(LED_RED_PIN, OUTPUT);
  pinMode(LED_GREEN_PIN, OUTPUT);
  pinMode(LED_BLUE_PIN, OUTPUT);
#endif
  pinMode(POT_PIN, INPUT);

  Wire.begin();

  // OLED（U8x8 纯文本模式）
  u8x8.begin();
  u8x8.setPowerSave(0);
  u8x8.setFont(u8x8_font_chroma48medium8_r);
  u8x8.setContrast(180);

  // 加速度计初始化（倾斜/敲击需要，失败不阻塞主流程）
  accelOk = initAccel();
  if (accelOk) {
    calibrateTilt();
  }

  screenStateStart = millis();
  lastLedUpdate = millis();
  lastKnobRead = millis();
}

void loop() {
  readSerialCommands();
  sampleButton();
  checkLongPress();
  resolvePendingClicks();
  processKnob();
  processAccel();
  updateBuzzer();
  updateLed();
  updateScreen();
}
