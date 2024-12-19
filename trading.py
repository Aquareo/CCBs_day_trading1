'''
根据可转债延后股票的动量特征策略
'''
import pandas as pd
import time
from datetime import datetime,timedelta
import pytz
import akshare as ak
import sys


# 获取年月日（返回 datetime.date 类型）
def get_date():
    local_timezone = pytz.timezone('Asia/Shanghai')  # 设置为你所在的时区（比如中国时间）
    local_time = datetime.now(local_timezone)  # 获取本地时区的当前时间
    
    # 提取日期部分，返回 datetime.date 类型
    return local_time.date()

#获取时分秒
def get_time():
    # 获取本地时间
    local_timezone = pytz.timezone('Asia/Shanghai')  # 设置为你所在的时区（比如中国时间）
    local_time = datetime.now(local_timezone)  # 获取本地时区的当前时间
    
    #这是时分秒
    current_time = local_time.strftime('%H:%M:%S')
    current_time_obj = datetime.strptime(current_time, '%H:%M:%S').time()
    return current_time_obj

def get_all_symbols():
    spot_df = ak.bond_zh_hs_cov_spot()
    symbols = spot_df['symbol'].values
    return symbols


def get_target_symbols(day_n=3,threshod=200000):
    # 目标债券符号列表
    target_symbols = []

    # 获取所有债券符号
    all_symbols = get_all_symbols()


    # 遍历所有债券符号
    for i in all_symbols:
        try:
            # 获取每个债券的历史数据
            temp = ak.bond_zh_hs_cov_daily(symbol=i)

            #先看是否到期
            if temp.iloc[-1].date<get_date() - timedelta(days=1):
                print(f"转债{i}已经到期，跳过此转债。")
                continue

            # 检查历史数据是否存在
            if temp is not None and len(temp) >= day_n:
                # 获取最后三天的成交量数据
                volumes = temp['volume'].tail(day_n).values  # 取最后day_n行的成交量数据
                closes = temp['close'].tail(day_n).values

                #每日日内的浮动大小
                changes=(temp['high'].tail(day_n).values-temp['low'].tail(day_n).values)/temp['open'].tail(day_n).values*100


                # 如果最后day_n天的成交量都大于threshod，加入target_symbols
                if all(volume > threshod for volume in volumes)and all(close <150 for  close in closes)and all( change>3 for  change in changes):
                    print(f"债券{i}加入目标")
                    target_symbols.append(i)
            else:
                print(f"债券{i} 的历史数据不足{day_n}天，跳过此债券。")
        
        except Exception as e:
            # 捕获异常并打印错误信息
            print(f"获取债券 {i} 的数据时出错: {e}")

        sys.stdout.flush()
    
    return target_symbols


def get_filtered_df(symbols):
    #处理一下，只留下数字，因为ak.bond_cov_comparison()的转债代码是只有数字的
    
    # 禁用 SettingWithCopyWarning 警告
    pd.options.mode.chained_assignment = None
    
    symbols = [s[2:] for s in symbols]

    df = ak.bond_cov_comparison()

    columns_to_convert = ['转债最新价', '转债涨跌幅', '正股最新价', '正股涨跌幅', '转股价', '转股溢价率']

    # 将这些列转换为数值类型，遇到无法转换的会被设置为 NaN
    df[columns_to_convert] = df[columns_to_convert].apply(pd.to_numeric, errors='coerce')

    # 重命名列 "转债最新价" 为 "trade"，为了跟online_trading里面对应，懒得改了
    df = df.rename(columns={"转债最新价": "trade", "转债代码": "symbol"})

    filtered_df = df[df['symbol'].isin(symbols)]
    
    filtered_df['落差涨跌幅']=filtered_df['正股涨跌幅']-filtered_df['转债涨跌幅']

    return filtered_df


def online_day_trading():
    
    # Initial Setup
    initial = 10000  # Initial capital
    share = 0  # Shares held
    asset = initial  # Portfolio value
    backtest = []  # Store backtest results

    today = datetime.today().strftime('%Y-%m-%d')  # Set today's date
    print("今天:", today)
    sys.stdout.flush()
           
    # Set up logging file path
    log_file = f"{today} 成交量策略 交易过程.txt"

    i = 0
    trading_cost=0
    while True:
        # Get the current time
        current_time = get_time()
        
        # Check if current time is within the allowed trading hours
        # Morning: 09:30 - 11:30, Afternoon: 13:00 - 15:00
        if (current_time >= datetime.strptime('09:30', '%H:%M').time() and current_time <= datetime.strptime('11:30', '%H:%M').time()) or \
        (current_time >= datetime.strptime('13:00', '%H:%M').time() and current_time <= datetime.strptime('15:00', '%H:%M').time()):

            print("时间为:", current_time)
            print(" ")

            filtered_df =  get_filtered_df(symbols)
            #display(filtered_df)
            
            # 找到差值最大的行
            target=filtered_df.loc[filtered_df['落差涨跌幅'].idxmax()]


            #首次交易
            if i == 0:
                # First buy
                old_price = target['trade']
                old_symbol = target['symbol']


                """
                买入操作
                """

                share = asset // old_price  # Calculate how many shares can be bought
                trading_cost+=share*old_price*0.0003
                output = f"时间为：{current_time}\n买入 {old_symbol} {share} 股 总资产: {asset}\n\n"
                print(output)

            else:
                # Update asset based on price change and possibly switch bond
                current_price = target['trade']
                current_symbol = target['symbol']
                new_price = filtered_df.loc[filtered_df['symbol'] == old_symbol]['trade'].values[0]
                asset += share * (new_price - old_price)  # Update asset value

                #如果需要换持有转债

                """
                买入操作+卖出操作
                """

                if current_symbol != old_symbol:
                    # Sell old and buy new bond
                    share = asset // current_price  # Recalculate shares for new bond
                    trading_cost+=share*current_price *0.0003
                    
                    output = f"时间为：{current_time}\n清仓 {old_symbol} 买入 {current_symbol} {int(share)} 股 总资产: {asset:.2f}\n\n"
                    print(output)
                    
                old_price = current_price
                old_symbol = current_symbol

            i += 1
            backtest.append(asset)  # Append updated asset
    

            print("持有可转债价格为:",old_price )
            print("总资产为：", asset)
            print("trading cost",trading_cost)
            # Pause for 25 seconds before the next transaction
            time.sleep(55)  # Pause for 30 seconds

        else:
            # If it's outside of trading hours, wait and check again after a short interval
            print("不在交易时间，等待下一个检查...")
            time.sleep(60)  # Pause for 60 seconds before checking again

        print(" ")
        sys.stdout.flush()


print("获取目标可转债池中...")
symbols=get_target_symbols()

#symbols=['sh110097', 'sh111012', 'sh111019', 'sh113530', 'sh113688', 'sh118003', 'sh118026', 'sz123018', 'sz123103', 'sz123138', 'sz123142', 'sz123163', 'sz123177', 'sz123237', 'sz128044', 'sz128066', 'sz128083', 'sz128085', 'sz128100']

# 打印符合条件的债券符号
print("符合条件的债券符号为:")
print(symbols)

online_day_trading()
