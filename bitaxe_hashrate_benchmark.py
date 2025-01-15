import requests
import time
import json
import signal
import sys
import argparse
import statistics

# ANSI Color Codes
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"

# Add this before the configuration section
def parse_arguments():
    parser = argparse.ArgumentParser(description='Bitaxe Hashrate Benchmark Tool')
    parser.add_argument('bitaxe_ip', nargs='?', help='IP address of the Bitaxe (e.g., 192.168.2.26)')
    parser.add_argument('-v', '--voltage', type=int, default=1150,
                       help='Initial voltage in mV (default: 1150)')
    parser.add_argument('-f', '--frequency', type=int, default=500,
                       help='Initial frequency in MHz (default: 500)')
    
    # If no arguments are provided, print help and exit
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)
    
    return parser.parse_args()

class particle_swarm():
    def __init__(self,n,factor,input_dims,history):
        self.history_size = history
        self.particles_n = n
        self.factor  = factor
        self.score_history = [[] for i in range (n)] # ouput
        self.domain_history = [[] for i in range (n)] # input
        self.current_particle_i = 0
        self.last_update = [[0 for i in range(n)] for i in range (input_dims)]

    def add_new_postion_score(self,paticle_i,domain,score):
        self.score_history[paticle_i].append(score)
        self.domain_history[paticle_i].append(domain)

        over_history = len(self.score_history[paticle_i]) > self.history_size
        if over_history:
            self.score_history[paticle_i] = self.score_history[paticle_i][-self.history_size:]
            self.domain_history[paticle_i] = self.domain_history[paticle_i][-self.history_size:]
        

    def get_best_input(self):
        best_score_per_particle = [max(i) for i in self.score_history]
        best_score = max(best_score_per_particle)

        #where
        best_particle = best_score_per_particle.index(best_score)
        best_loc = self.score_history[best_particle].index(best_score)

        self.best_score = best_score
        self.best_domain = self.domain_history[best_particle][best_loc]

        return self.best_domain

    def update_postiton(self,particle_i):
        self.get_best_input()
        best_pos = self.best_domain
        current_pos = self.domain_history[particle_i][-1]

        if best_pos == current_pos: 
            # basic extrapolation
            new_position = []
            for i,last_updates in enumerate(self.last_update):
                mean_update = statistics.mean(last_updates)
                new_pos = current_pos[i] + mean_update*self.factor
                new_position.append(new_pos)
                self.last_update[i][particle_i] = mean_update
            return new_position

        new_position = []
        for i,(j,k) in enumerate(zip(current_pos,best_pos)):
            direction = (k - j)/abs(k - j)
            distance = self.factor*abs(k-j)
            new_pos = j + direction*distance
            new_position.append(new_pos)
            self.last_update[i][particle_i] = direction*distance
        return new_position
    
    def next_particle(self):
        self.current_particle_i = (self.current_particle_i + 1) % self.particles_n

# Replace the configuration section
args = parse_arguments()
bitaxe_ip = f"http://{args.bitaxe_ip}"
initial_voltage = args.voltage
initial_frequency = args.frequency

# Configuration
voltage_increment = 25
frequency_increment = 25
sample_interval = 30   # 30 seconds sample interval
max_temp = 66         # Will stop if temperature reaches or exceeds this value
max_allowed_voltage = 1400
max_allowed_frequency = 1200
max_vr_temp = 90  # Maximum allowed voltage regulator temperature


# Optimiser Configuration
# target
optimisation_target = "hashrate_efficiancy"

# only used for some settings of hashrate_efficiancy
# this is optimised for first, then another thing is optimised
control_temp = 50
control_hashrate = 500 


# how long each iteration should take
sample_interval = 30
benchmark_iteration_time = sample_interval*5

# setup optimiser
# if you dont want to use the optimiser set to false
# at the same time increase n_particles
# this will have the effect of behaving like grid search 
use_optimiser = True

#used for grid search and optimiser
n_particles = 5

# optimiser configs
optimiser_time = 3600 #1H
convergence_factor = 0.05
particle_inputs = 2
pariticle_history = 10
ps_optimiser= particle_swarm(n_particles,convergence_factor,particle_inputs,pariticle_history)

# Add these variables to the global configuration section
small_core_count = None
asic_count = None

# Validate core voltages
if initial_voltage > max_allowed_voltage:
    raise ValueError(RED + f"Error: Initial voltage exceeds the maximum allowed value of {max_allowed_voltage}mV. Please check the input and try again." + RESET)

# Validate frequency
if initial_frequency > max_allowed_frequency:
    raise ValueError(RED + f"Error: Initial frequency exceeds the maximum allowed value of {max_allowed_frequency}Mhz. Please check the input and try again." + RESET)

# Results storage
results = []

# Dynamically determined default settings
default_voltage = None
default_frequency = None

def fetch_default_settings():
    global default_voltage, default_frequency, small_core_count, asic_count
    try:
        response = requests.get(f"{bitaxe_ip}/api/system/info", timeout=10)
        response.raise_for_status()
        system_info = response.json()
        default_voltage = system_info.get("coreVoltage", 1250)  # Fallback to 1250 if not found
        default_frequency = system_info.get("frequency", 550)  # Fallback to 550 if not found
        small_core_count = system_info.get("smallCoreCount", 0)
        asic_count = system_info.get("asicCount", 0)
        print(GREEN + f"Default settings determined:\n"
                      f"  Core Voltage: {default_voltage}mV\n"
                      f"  Frequency: {default_frequency}MHz\n"
                      f"  ASIC Configuration: {small_core_count * asic_count} total cores" + RESET)
    except requests.exceptions.RequestException as e:
        print(RED + f"Error fetching default system settings: {e}. Using fallback defaults." + RESET)
        default_voltage = 1200
        default_frequency = 550
        small_core_count = 0
        asic_count = 0

# Add a global flag to track whether the system has already been reset
system_reset_done = False

def handle_sigint(signum, frame):
    global system_reset_done
    if not system_reset_done:
        print(RED + "Benchmarking interrupted by user." + RESET)
        if results:
            reset_to_best_setting()
            save_results()
            print(GREEN + "Bitaxe reset to best or default settings and results saved." + RESET)
        else:
            print(YELLOW + "No valid benchmarking results found. Applying predefined default settings." + RESET)
            set_system_settings(default_voltage, default_frequency)
            restart_system()
        system_reset_done = True
    sys.exit(0)

# Register the signal handler
signal.signal(signal.SIGINT, handle_sigint)

def get_system_info():
    retries = 3
    for attempt in range(retries):
        try:
            response = requests.get(f"{bitaxe_ip}/api/system/info", timeout=10)
            response.raise_for_status()  # Raise an exception for HTTP errors
            return response.json()
        except requests.exceptions.Timeout:
            print(YELLOW + f"Timeout while fetching system info. Attempt {attempt + 1} of {retries}." + RESET)
        except requests.exceptions.ConnectionError:
            print(RED + f"Connection error while fetching system info. Attempt {attempt + 1} of {retries}." + RESET)
        except requests.exceptions.RequestException as e:
            print(RED + f"Error fetching system info: {e}" + RESET)
            break
        time.sleep(5)  # Wait before retrying
    return None

def set_system_settings(core_voltage, frequency):
    settings = {
        "coreVoltage": core_voltage,
        "frequency": frequency
    }
    try:
        response = requests.patch(f"{bitaxe_ip}/api/system", json=settings, timeout=10)
        response.raise_for_status()  # Raise an exception for HTTP errors
        print(YELLOW + f"Applying settings: Voltage = {core_voltage}mV, Frequency = {frequency}MHz" + RESET)
        time.sleep(2)
        restart_system()
    except requests.exceptions.RequestException as e:
        print(RED + f"Error setting system settings: {e}" + RESET)

def restart_system():
    try:
        print(YELLOW + "Restarting Bitaxe system to apply new settings..." + RESET)
        response = requests.post(f"{bitaxe_ip}/api/system/restart", timeout=10)
        response.raise_for_status()  # Raise an exception for HTTP errors
        time.sleep(60)  # Allow 60s time for the system to restart and start hashing
    except requests.exceptions.RequestException as e:
        print(RED + f"Error restarting the system: {e}" + RESET)

def benchmark_iteration(core_voltage, frequency,sample_interval,benchmark_time):
    print(GREEN + f"Starting benchmark for Core Voltage: {core_voltage}mV, Frequency: {frequency}MHz" + RESET)
    times = []
    nonces = []
    temperatures = []
    power_consumptions = []
    vcores = []
    total_samples = benchmark_time // sample_interval

    

    # Calculate expected hashrate based on frequency
    expected_hashrate_mhs = frequency * ((small_core_count * asic_count) / 1000000)

    # First step of benchmarking 
    # find stable temps
    temp_data = []
    while True:

        info = get_system_info()
        temp_data.append(info['temp'])

        if len(temp_data) > 5:
            _avg = sum(temp_data[-5:])/5
            print(f'finding stable temps last:{temp_data[-1]} avg:{_avg}')
            if abs(temp_data[-1] - _avg) < 0.1: break

            # early exit
            # cool dont bother chip refused combination
            temp_threshold = 39
            if temp_data[-1] < temp_threshold: 
                return None, None, None, False 
        time.sleep(3)


    info = get_system_info()
    starting_nonce_offset = info['sharesAccepted']
    t0 = time.time()
    
    # Collect samples
    # samples are autocorrelated because of window function used for 10m 
    # samples are only independant after 10m
    # Temps,vrTemp,coreMv are independant and are useful
    for sample in range(total_samples):
        info = get_system_info()
        if info is None:
            print(YELLOW + "Skipping this iteration due to failure in fetching system info." + RESET)
            return None
        
        temp = info.get("temp")
        vr_temp = info.get("vrTemp")  # Get VR temperature if available
        
        if temp is None:
            print(YELLOW + "Temperature data not available." + RESET)
            return None
        
        # Check both chip and VR temperatures
        if temp >= max_temp:
            print(RED + f"Chip temperature exceeded {max_temp}°C! Stopping current benchmark." + RESET)
            return None
            
        if vr_temp is not None and vr_temp >= max_vr_temp:
            print(RED + f"Voltage regulator temperature exceeded {max_vr_temp}°C! Stopping current benchmark." + RESET)
            return None
        
        hash_rate = info.get("hashRate")
        power_consumption = info.get("power")
        
        if hash_rate is None or power_consumption is None:
            print(YELLOW + "Hashrate or Watts data not available." + RESET)
            return None
        

        nonces.append(info.get("sharesAccepted"))
        times.append(time.time()-t0)

        vcores.append(info.get("coreVoltageActual"))
        temperatures.append(temp)
        power_consumptions.append(power_consumption)
        
        # Calculate percentage progress
        percentage_progress = ((sample + 1) / total_samples) * 100

        elapsed = time.time()-t0
        status_line = (
            f"[{sample + 1:2d}/{total_samples:2d}] {elapsed:04}s "
            f"{percentage_progress:5.1f}% | "
            f"V: {core_voltage:4d}mV | "
            f"F: {frequency:4d}MHz | "
            f"H: {int(hash_rate):4d} GH/s | "
            f"T: {int(temp):2d}°C"
        )
        if vr_temp is not None and vr_temp > 0:
            status_line += f" | VR: {int(vr_temp):2d}°C"
        print(YELLOW + status_line + RESET)
        
        # Only sleep if it's not the last iteration
        if sample < total_samples - 1:
            time.sleep(sample_interval)
    
    
    # Statistics time
    elapsed = time.time()-t0
    pool_diff = 256

    # calc our own hashrate we know the pool diff is 256 as we have test pool
    hashrate_mhs = pool_diff*(info.get("sharesAccepted")-starting_nonce_offset)/elapsed/10000000

    
    vcore_avg = statistics.mean(vcores)
    vcore_std = statistics.stdev(vcores)
    v_core_stray = abs(info.get("vcore")-vcore_avg)

    temp_max = max(temperatures)
    temp_avg = statistics.mean(temperatures)
    temp_std = statistics.stdev(temperatures)

    power_avg = statistics.mean(power_consumption)
    power_std = statistics.stdev(power_consumption)


    # Normalised score as we have same data it will converge to the luck of the work items
    efficiency_jth = power_avg / (hashrate_mhs / 1000000)

    print(GREEN + f"Average Hashrate: {hashrate_mhs:.2f} GH/s (Expected: {expected_hashrate_mhs:.2f} GH/s)" + RESET)
    print(GREEN + f"Average Temperature: {temp_avg:.2f}°C" + RESET)
    print(GREEN + f"Efficiency: {efficiency_jth:.2f} J/TH" + RESET)

    # Keep all data for plotting
    return  (hashrate_mhs, temp_avg, efficiency_jth, power_avg, temp_std, v_core_stray, vcore_std, power_std)
    

def save_results():
    try:
        # Extract IP from bitaxe_ip global variable and remove 'http://'
        ip_address = bitaxe_ip.replace('http://', '')
        filename = f"bitaxe_benchmark_results_{ip_address}.json"
        with open(filename, "w") as f:
            json.dump(results, f, indent=4)
        print(GREEN + f"Results saved to {filename}" + RESET)
    except IOError as e:
        print(RED + f"Error saving results to file: {e}" + RESET)

def reset_to_best_setting():
    if not results:
        print(YELLOW + "No valid benchmarking results found. Applying predefined default settings." + RESET)
        set_system_settings(default_voltage, default_frequency)
    else:
        best_result = sorted(results, key=lambda x: x["averageHashRate"], reverse=True)[0]
        best_voltage = best_result["coreVoltage"]
        best_frequency = best_result["frequency"]

        print(GREEN + f"Applying the best settings from benchmarking:\n"
                      f"  Core Voltage: {best_voltage}mV\n"
                      f"  Frequency: {best_frequency}MHz" + RESET)
        set_system_settings(best_voltage, best_frequency)
    
    restart_system()



def cost_function(avg_hashrate,expected_hashrate, control_hashrate, avg_temp,control_temp, efficiency_jth,target):

    hashrate_ratio = avg_hashrate/expected_hashrate

    if target == "efficiancy":
        return efficiency_jth
    
    elif target == "hashrate":
        return avg_hashrate
    
    elif target == "hashrate_expected":
        return hashrate_ratio

    elif target == "hashrate_temp":
        return abs(control_temp/avg_temp)+avg_hashrate
    
    elif target == "hashrate_efficiancy":
        return abs(control_hashrate/avg_hashrate)+efficiency_jth/20

    elif target == "efficiancy_temp":
        return abs(control_temp/avg_temp)+hashrate_ratio
    
    elif target == "custom":
        # add your own
        pass
    
    # Default - hashrate
    return avg_hashrate


def start_benchmarking():

    # make bounds
    vcore_range = max_allowed_voltage-initial_voltage
    freq_range = max_allowed_frequency-initial_frequency

    vcore_offset = vcore_range//n_particles
    freq_offset = freq_range//n_particles

    # make inital positions
    queue = [
                [
                    initial_frequency+freq_offset*i,
                    initial_voltage+vcore_offset*i
                ] for i in range(n_particles)
            ]


    start_optimisation_time = time.time()

    best_history = []

    # Main benchmarking process
    try:
        fetch_default_settings()
        
        # Add disclaimer
        print(RED + "\nDISCLAIMER:" + RESET)
        print("This tool will stress test your Bitaxe by running it at various voltages and frequencies.")
        print("While safeguards are in place, running hardware outside of standard parameters carries inherent risks.")
        print("Use this tool at your own risk. The author(s) are not responsible for any damage to your hardware.")
        print("\nNOTE: Ambient temperature significantly affects these results. The optimal settings found may not")
        print("work well if room temperature changes substantially. Re-run the benchmark if conditions change.\n")
        
        
        while (time.time()-start_optimisation_time<optimiser_time):
            
            # Refill item in queue
            if len(queue)==0:
                new_position = ps_optimiser.update_postiton(ps_optimiser.current_particle_i)
                queue.append(new_position)

                if not use_optimiser: 
                    # after we ge to the point of needing new points our grid search is over
                    break

            # Main optimisation step
            current_pos = queue[0]
            current_frequency,current_voltage = current_pos
            set_system_settings(current_voltage, current_frequency)

            # calulate expected
            expected_hashrate_mhs = expected_hashrate_mhs = current_frequency * ((small_core_count * asic_count) / 1000000)

            # make sample
            result_data = benchmark_iteration(current_voltage, current_frequency,sample_interval,benchmark_iteration_time)

            if result_data:
                # update optimiser, since optimiser will try same again (deterministic) if failed we dont need retry loop
                # this is where we get our score for the optimiser
                score = cost_function(hashrate_mhs,expected_hashrate_mhs,control_hashrate,temp_avg,control_temp,efficiency_jth,optimisation_target)
                ps_optimiser.add_new_postion_score(ps_optimiser.current_particle_i,current_pos,score)
                ps_optimiser.next_particle()
                ps_optimiser.get_best_input()
                
                if ps_optimiser.best_score > max([i[1] for i in best_history]):
                    best_history.append([ps_optimiser.best_domain,ps_optimiser.best_score])

                if len(best_history)==0:
                    best_history.append([ps_optimiser.best_domain,ps_optimiser.best_score])



            elif result_data is None:
                (hashrate_mhs, temp_avg, efficiency_jth,power_avg,temp_std,v_core_stray,vcore_std,power_std) = 0,0,0,0,0,0,0

            
            # used the item in the queue
            if use_optimiser:
                queue.remove(queue[0])

            else:
                # for the grid search oply remove if we have data
                if result_data:
                    queue.remove(queue[0])


            if result_data:
                results.append({
                    "coreVoltage": current_voltage,
                    "frequency": current_frequency,
                    "averageHashRate": hashrate_mhs,
                    "averageTemperature": temp_avg,
                    "efficiencyJTH": efficiency_jth,
                    "powerAvg": power_avg,
                    "tempStd": temp_std,
                    "vcoreStray": v_core_stray, # how far from real value
                    "vcoreStd": vcore_std,
                    "powerStd": power_std,
                    "control_temp": control_temp,
                    "control_hashrate": control_hashrate,
                    "target": optimisation_target,
                    "BenchmarkingTime": optimiser_time,
                    "Sample_interval": sample_interval,
                    "SampleTime": benchmark_iteration_time,

                })

            else:
                # If we hit thermal limits or other issues, we've found the highest safe settings
                print(GREEN + "Reached thermal or stability limits. Stopping further testing." + RESET)
                break  # Stop testing higher values

            save_results()

    except Exception as e:
        print(RED + f"An unexpected error occurred: {e}" + RESET)
        if results:
            reset_to_best_setting()
            save_results()
        else:
            print(YELLOW + "No valid benchmarking results found. Applying predefined default settings." + RESET)
            set_system_settings(default_voltage, default_frequency)
            restart_system()
    finally:
        if not system_reset_done:
            if results:
                reset_to_best_setting()
                save_results()
                print(GREEN + "Bitaxe reset to best or default settings and results saved." + RESET)
            else:
                print(YELLOW + "No valid benchmarking results found. Applying predefined default settings." + RESET)
                set_system_settings(default_voltage, default_frequency)
                restart_system()
            system_reset_done = True

        # Print results summary only if we have results
        if results:
            # Sort results by averageHashRate in descending order and get the top 5
            top_5_results = sorted(results, key=lambda x: x["averageHashRate"], reverse=True)[:5]
            
            # Create a dictionary containing all results and top performers
            final_data = {
                "all_results": results,
                "top_performers": [
                    {
                        "rank": i,
                        "coreVoltage": result["coreVoltage"],
                        "frequency": result["frequency"],
                        "averageHashRate": result["averageHashRate"],
                        "averageTemperature": result["averageTemperature"],
                        "efficiencyJTH": result["efficiencyJTH"],
                        "powerAvg": result["powerAvg"],
                        "vcoreStray": result["vcoreStray"]
                    }
                    for i, result in enumerate(top_5_results, 1)
                ]
            }
            
            # Save the final data to JSON
            ip_address = bitaxe_ip.replace('http://', '')
            filename = f"bitaxe_benchmark_results_{ip_address}.json"
            with open(filename, "w") as f:
                json.dump(final_data, f, indent=4)
            
            print(GREEN + "Benchmarking completed." + RESET)
            if top_5_results:
                print(GREEN + "\nTop 5 Performing Settings:" + RESET)
                for i, result in enumerate(top_5_results, 1):
                    print(GREEN + f"\nRank {i}:" + RESET)
                    print(GREEN + f"  Core Voltage: {result['coreVoltage']}mV + {result['vcoreStray']}mv" + RESET)
                    print(GREEN + f"  Frequency: {result['frequency']}MHz" + RESET)
                    print(GREEN + f"  Average Hashrate: {result['averageHashRate']:.2f} GH/s" + RESET)
                    print(GREEN + f"  Average Temperature: {result['averageTemperature']:.2f}°C" + RESET)
                    print(GREEN + f"  Efficiency: {result['efficiencyJTH']:.2f} J/TH" + RESET)
            else:
                print(RED + "No valid results were found during benchmarking." + RESET)


if __name__ == "__main__":
    #start_server() # need to update pool setting in bitaxe
    start_benchmarking()