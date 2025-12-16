import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

class AuctionProcessSimulator:
    def __init__(self, data_file_path, verbose=False):
        """ Initialising and Loading """
        self.data_file_path = data_file_path
        self.verbose = verbose
        
        self.dfs = pd.read_excel(self.data_file_path, sheet_name=['windplants', 'wind_loadfactors', 'solarplants', 'solar_loadfactors', 'gasplants', 'demand', 'gas_prices'])

        self.df_wind_plants = self.dfs['windplants']
        self.df_wind_lf = self.dfs['wind_loadfactors']
        self.df_solar_plants = self.dfs['solarplants']
        self.df_solar_lf = self.dfs['solar_loadfactors']
        self.df_gas_plants = self.dfs['gasplants']
        self.df_demand = self.dfs['demand']
        self.df_gas_prices = self.dfs['gas_prices']


        self.validation()
        self.calculation()


    def validation(self):

        standard_hours = self.df_demand['hour'].values
        
        checking = {'Gas Prices': self.df_gas_prices['hour'].values,
                    'Wind LoadFactors': self.df_wind_lf['hour'].values,
                    'Solar LoadFactors': self.df_solar_lf['hour'].values}

        for names, hours in checking.items():
            if not np.array_equal(standard_hours, hours):
                raise ValueError(f"Data Error: '{names}' hours do not align with Demand hours.")
        
        if self.verbose:
            print("Data alignment checked.")



    def calculation(self):
        wind_capacities = self.df_wind_plants['capacity'].values
        solar_capacities = self.df_solar_plants['capacity'].values
        
        wind_plant_names = self.df_wind_plants['name'].tolist()
        solar_plant_names = self.df_solar_plants['name'].tolist()

        wind_lf_matrix = self.df_wind_lf[wind_plant_names].values
        solar_lf_matrix = self.df_solar_lf[solar_plant_names].values

        self.total_wind_generated = wind_lf_matrix.dot(wind_capacities)
        self.total_solar_generated = solar_lf_matrix.dot(solar_capacities)

        #Net Demand
        self.net_demand = self.df_demand['demand'].values - self.total_wind_generated - self.total_solar_generated

        # Merit Order
        self.sorted_gas_plants = self.df_gas_plants.sort_values(by='efficiency', ascending=False).reset_index(drop=True)

        self.capacity_stack = self.sorted_gas_plants['capacity'].values
        self.efficiency_stack = self.sorted_gas_plants['efficiency'].values

        if self.verbose:
          print(f"Max Net Demand: {self.net_demand.max()}")
          print(f"Min Net Demand: {self.net_demand.min()}")

    def simulation(self):
        """ Simulating """
        results = []

        # Simulation Loop
        for i in range(len(self.df_demand)):
            current_net_demand = self.net_demand[i]
            gas_price = self.df_gas_prices.loc[i, 'price']

            marginal_price = 0.0
            gas_generation_total = 0.0

            # 1. Curtailment, when Supply > Demand
            if current_net_demand <= 0: 
                marginal_price = 0.0
                gas_generation_total = 0.0
            
            # 2. Most conditions, when Supply <= Demand
            else:
                conversion = gas_price / 100 * 34.121  # from pence per Therm to pound MWh
                bids = conversion / self.efficiency_stack
                
                remaining_demand = current_net_demand

                # level up
                for gas_plant_index, gas_plant_capacity in enumerate(self.capacity_stack):
                    if remaining_demand <= 0:
                        break

                    dispatch_amount = min(gas_plant_capacity, remaining_demand) 
                    remaining_demand -= dispatch_amount 
                    gas_generation_total += dispatch_amount

                    marginal_price = bids[gas_plant_index] 

                    # 3. The worst condition, when there is a Supply Shortage
                if remaining_demand > 0 and self.verbose:
                    print(f"WARNING: Hour {self.df_demand.loc[i, 'hour']} has supply shortage of {remaining_demand:.2f} MWh.")


            total_supply = self.total_wind_generated[i] + self.total_solar_generated[i] + gas_generation_total
            shortage_amount = max(0, self.df_demand.loc[i, 'demand'] - total_supply)

            results.append({
                'Hour': self.df_demand.loc[i, 'hour'],
                'Marginal_Price_GBP': marginal_price,
                'Wind_Generated_MWh': self.total_wind_generated[i],
                'Solar_Generated_MWh': self.total_solar_generated[i],
                'Gas_Generated_MWh': gas_generation_total,
                'Demand_MWh': self.df_demand.loc[i, 'demand'],
                'Supply_Shortage_MWh': shortage_amount
            })

        # DataFrame
        self.df_results = pd.DataFrame(results)

        if self.verbose:
          print(self.df_results.to_string(index=False)) 
          print(f"Average Price: £{self.df_results['Marginal_Price_GBP'].mean():.2f}/MWh")
        else:
          print(f"Average Price: £{self.df_results['Marginal_Price_GBP'].mean():.2f}/MWh")


        shortage_hours = (self.df_results['Supply_Shortage_MWh'] > 0).sum()
        if shortage_hours > 0:
          print(f"WARNING: System Shortage detected in {shortage_hours} hours.")
        
        return self.df_results

    def report(self, filename='hourly_prices_and_mix_report.csv'):
        if hasattr(self, 'df_results'):
            self.df_results.to_csv(filename, index=False)
            print(f"Results saved to {filename}")
        else:
            print("Error: No results to save. Run simulation first.")

    def plot(self):
        if not hasattr(self, 'df_results'):
            print("Please run simulation first.")
            return

        df = self.df_results
        

        hours = df['Hour']
        wind = df['Wind_Generated_MWh']
        solar = df['Solar_Generated_MWh']
        gas = df['Gas_Generated_MWh']
        demand = df['Demand_MWh']
        price = df['Marginal_Price_GBP']


        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True, gridspec_kw={'height_ratios': [2, 1]})

        #plot
        ax1.stackplot(hours, wind, solar, gas,
                      labels=['Wind', 'Solar', 'Gas'],
                      colors=['#1f77b4', '#ff7f0e', '#d62728'], alpha=0.8)

        ax1.plot(hours, demand, color='black', linewidth=2, linestyle='--', label='Total Demand')

        total_supply = wind + solar + gas
        ax1.fill_between(hours, total_supply, demand, 
                         where=(demand > total_supply), 
                         interpolate=True, color='red', alpha=0.3, hatch='//', label='Shortage')
        
        ax1.legend(loc='upper left')
        ax1.set_title('Hourly Dispatch Mix vs Total Demand (Stackplot)', fontsize=14)
        ax1.set_ylabel('Total Supply (MWh)', fontsize=12)
        ax1.legend(loc='upper left')
        ax1.grid(True, alpha=0.3)


        ax2.plot(hours, price, color='purple', linewidth=2, label='Market Price')

        zero_price_data = df[df['Marginal_Price_GBP'] == 0]
        ax2.scatter(zero_price_data['Hour'], zero_price_data['Marginal_Price_GBP'],
                    color='red', s=30, zorder=5, label='Zero Price')

        ax2.set_title('Electricity Market Price (£/MWh)', fontsize=14)
        ax2.set_xlabel('Hour', fontsize=12)
        ax2.set_ylabel('Price (£/MWh)', fontsize=12)
        ax2.grid(True, alpha=0.3)
        ax2.legend()

        plt.tight_layout()
        plt.savefig("dispatch_and_price.png", dpi=150)
        plt.show()


#  Execution
if __name__ == "__main__":

    simulator = AuctionProcessSimulator("data2.xlsx")
    
    df_results = simulator.simulation()
    
    simulator.report()

    simulator.plot()



