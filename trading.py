'''
根据股票和可转债的关系来操作
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
    """获取并过滤符合条件的转债数据"""
    pd.options.mode.chained_assignment = None  # 禁用 SettingWithCopyWarning
    symbols = [s[2:] for s in symbols]  # 处理转债代码，取后面数字部分

    try:
        # 获取数据
        df = ak.bond_cov_comparison()

        # 转换需要的列为数值类型
        columns_to_convert = ['转债最新价', '转债涨跌幅', '正股最新价', '正股涨跌幅', '转股价', '转股溢价率']
        df[columns_to_convert] = df[columns_to_convert].apply(pd.to_numeric, errors='coerce')

        # 重命名列，便于后续使用
        df = df.rename(columns={"转债最新价": "trade", "转债代码": "symbol"})

        # 过滤目标符号的债券
        filtered_df = df[df['symbol'].isin(symbols)]

        # 计算正股和转债的涨跌幅差
        filtered_df['落差涨跌幅'] = filtered_df['正股涨跌幅'] - filtered_df['转债涨跌幅']

        return filtered_df

    except Exception as e:
        print(f"获取数据时出现错误: {e}")
        return pd.DataFrame()



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
            if filtered_df.empty:
                print("接口数据获取出错，请等待...")
                continue

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
#symbols=get_target_symbols()

symbols='''
获取每日的目标债券,成熟的方式
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
    """获取并过滤符合条件的转债数据"""
    pd.options.mode.chained_assignment = None  # 禁用 SettingWithCopyWarning
    symbols = [s[2:] for s in symbols]  # 处理转债代码，取后面数字部分

    try:
        # 获取数据
        df = ak.bond_cov_comparison()

        # 转换需要的列为数值类型
        columns_to_convert = ['转债最新价', '转债涨跌幅', '正股最新价', '正股涨跌幅', '转股价', '转股溢价率']
        df[columns_to_convert] = df[columns_to_convert].apply(pd.to_numeric, errors='coerce')

        # 重命名列，便于后续使用
        df = df.rename(columns={"转债最新价": "trade", "转债代码": "symbol"})

        # 过滤目标符号的债券
        filtered_df = df[df['symbol'].isin(symbols)]

        # 计算正股和转债的涨跌幅差
        filtered_df['落差涨跌幅'] = filtered_df['正股涨跌幅'] - filtered_df['转债涨跌幅']

        return filtered_df

    except Exception as e:
        print(f"获取数据时出现错误: {e}")
        return pd.DataFrame()



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
            if filtered_df.empty:
                print("接口数据获取出错，请等待...")
                continue

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
#symbols=get_target_symbols()

symbols=['sh111012', 'sh111019', 'sh113688', 'sh118007', 'sh118026', 'sz123103', 'sz123138', 'sz123163', 'sz123184', 'sz123204', 'sz123228', 'sz123237', 'sz123239', 'sz127019', 'sz128083', 'sz128143']

# 打印符合条件的债券符号
print("符合条件的债券符号为:")
print(symbols)

online_day_trading()
# 打印符合条件的债券符号
print("符合条件的债券符号为:")
print(symbols)

online_day_trading()
