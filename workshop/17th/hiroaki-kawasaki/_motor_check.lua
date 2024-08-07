-- Lua script to write and read from a serial

---@diagnostic disable: need-check-nil

-- SCR_USER1: EXEC_MODE
-- SCR_USER2: EXP_RPM
-- SCR_USER3: OK_RANGE (percent)

local MODE_ACRO = 1
local EXEC_MODE = MODE_ACRO
local OUTPUT_PWM_DEFAULT = 1000 * 0.07 + 1000
local EXP_RPM_DEFAULT = 1500
local EXP_RPM = EXP_RPM_DEFAULT
local OK_RANGE_DEFAULT = 0.2
local OK_RANGE = OK_RANGE_DEFAULT

local port = serial:find_serial(0)
local motor_array = {0, 3, 1, 2}
local rx_data = {}
local rpm = {}

local tries = 0
local motor_index = -1

port:begin(115200)
port:set_flow_control(0)

local discard_bytes = 0
while port:available() > 0 do
  local byte = port:read()
  discard_bytes = discard_bytes + 1
end
gcs:send_text(0, ">> Discarded serial buffer: " .. discard_bytes)

local ok_count = 0
local last_mode = 0

-- Serial data format
-- 0  : 0xff const
-- 1-2: motor1 rpm
-- 3-4: motor2 rpm
-- 5-6: motot3 rpm
-- 7-8: motot4 rpm
-- 9  : sum(1 to 8)

function get_rpm()
  while port:available() > 0 do
    if port:available() >= 10 then  -- 必要なバイト数があるか確認

      -- 各バイトを整数に変換
      rx_data[1] = port:read()

      -- 最初のバイトが0xffであることを確認
      if rx_data[1] == 0xff then
        local sum = 0
        for i = 2, 9 do
          rx_data[i] = port:read()
          sum = (sum + rx_data[i]) & 0xff
        end

        rx_data[10] = port:read()
        if rx_data[10] == sum then
          -- 正しいデータを取得できたら、16ビット整数データを組み立てる
          for i = 1, 4 do
            rpm[i] = rx_data[i * 2] + (rx_data[i * 2 + 1] * 256)
          end
          return 0
        else
          -- データエラー時の処理
          gcs:send_text(0, "Data error: SUM mismatch  exp=" .. rx_data[10] .. "  sum=" .. sum)
        end
      else
        -- フォーマットエラー時、読み捨て
        gcs:send_text(0, "Data error: First byte is not 0xff, discarding byte")
      end
    else
      -- データが不足している場合の処理
      gcs:send_text(0, "Insufficient data available")
    end
  end
  return -1
end

-- データを読み込む関数
function task ()
  local current_mode = vehicle:get_mode()

  local output_pwm = OUTPUT_PWM_DEFAULT
  local mot_spin_arm = param:get('MOT_SPIN_ARM')
  if mot_spin_arm then
    output_pwm = 1000 * mot_spin_arm + 1000
  end

  local exec_mode = param:get('SCR_USER1')
  if exec_mode and exec_mode ~= 0 then
    EXEC_MODE = exec_mode
  else
    EXEC_MODE = MODE_ACRO
  end

  local exp_rpm = param:get('SCR_USER2')
  if exp_rpm and exp_rpm ~= 0 then
    EXP_RPM = exp_rpm
  else
    EXP_RPM = EXP_RPM_DEFAULT
  end

  local ok_range = param:get('SCR_USER3')
  if ok_range and ok_range ~= 0 then
    -- percent
    OK_RANGE = ok_range / 100
  else
    OK_RANGE = OK_RANGE_DEFAULT
  end

  if last_mode ~= EXEC_MODE and current_mode == EXEC_MODE then
    if  arming:is_armed() then
      gcs:send_text(0, "*** ERROR: Cannot execute when already armed")
    else
      motor_index = 1
      tries = 0
    end
  end
  last_mode = current_mode

  if motor_index > 0 then
    SRV_Channels:set_output_pwm_chan_timeout(motor_array[motor_index], output_pwm, 1100)
    tries = tries + 1
    if tries > 15 then
      gcs:send_text(0, "*** MTR" .. motor_index .. ": NG")
      motor_index = -1
    end
  end

  if get_rpm() >= 0 then    
    gcs:send_text(6, "rpm: " .. rpm[1] ..", ".. rpm[2] ..", " .. rpm[3] ..", " .. rpm[4])
    if motor_index > 0 then
      if rpm[motor_array[motor_index] + 1] > EXP_RPM * (1 - OK_RANGE) and rpm[motor_array[motor_index] + 1] < EXP_RPM * (1 + OK_RANGE) then
        ok_count = ok_count + 1
        if ok_count >= 3 then 
          gcs:send_text(0, ">>> MTR" .. motor_index .. ": OK")
          tries = 0
          ok_count = 0
          motor_index = motor_index + 1
          if motor_index > 4 then
            gcs:send_text(0, ">>> arming...")
            motor_index = -1
            arming:arm()
          end
        end
      else
        ok_count = 0
      end
    end
  end
  return task, 500
end

return task, 500
