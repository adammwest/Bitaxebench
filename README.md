# Bitaxe Hashrate Benchmark

A Python-based benchmarking tool for optimizing Bitaxe mining performance by testing different voltage and frequency combinations while monitoring hashrate, temperature, and power efficiency.

## Credits
- `Whitey Cookie`
- `mv777`
- `shufps`


## Features

- Automated benchmarking of different voltage/frequency combinations
- Temperature monitoring and safety cutoffs
- Power efficiency calculations (J/TH)
- Automatic saving of benchmark results
- Graceful shutdown with best settings retention
- Docker support for easy deployment
- Particle swarm optimisation
- Easy to implemnt cost functions
- Stable temps before sampling
- Independant hashrate samples only



## Optimiser
https://en.wikipedia.org/wiki/Particle_swarm_optimization
the optimiser is a global optimiser that has its inital postions spread out evenly, 
so should converge to the global minimum given we have smooth convex space to search

# Cost function
what the optimser tends towards
- `efficiancy` 
- `hashrate`
- `hashrate_expected` ratio of hashrate/expected hashrate
- `hashrate_temp` optimise temp to control temp and hashrate
- `hashrate_efficiancy` optimise hashrate to control temp and efficiancy
- `efficiancy_temp` optimise temp to control temp and efficiancy

you can add your own for any combination of 
[`efficiancy`, `temp`, `hashrate`]


## Prerequisites

- Python 3.11 or higher
- Access to a Bitaxe miner on your network
- Docker (optional, for containerized deployment)

## Installation

### Standard Installation

1. Clone the repository:
```bash
git clone https://github.com/mrv777/Bitaxe-Hashrate-Benchmark.git
cd Bitaxe-Hashrate-Benchmark
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
# On Windows
venv\Scripts\activate
# On Linux/Mac
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

### Docker Installation

1. Build the Docker image:
```bash
docker build -t bitaxe-benchmark .
```

## Usage

### Standard Usage

Run the benchmark tool by providing your Bitaxe's IP address:

```bash
python bitaxe_hashrate_benchmark.py <bitaxe_ip>
```

Optional parameters:
- `-v, --voltage`: Initial voltage in mV (default: 1150)
- `-f, --frequency`: Initial frequency in MHz (default: 500)

Example:
```bash
python bitaxe_hashrate_benchmark.py 192.168.2.26 -v 1200 -f 550
```

### Docker Usage

Run the container with your Bitaxe's IP address:

```bash
docker run --rm bitaxe-benchmark <bitaxe_ip> [options]
```

Example:
```bash
docker run --rm bitaxe-benchmark 192.168.2.26 -v 1200 -f 550
```

## Configuration

The script includes several configurable parameters:

- Maximum chip temperature: 66°C
- Maximum VR temperature: 90°C
- Maximum allowed voltage: 1300mV
- Maximum allowed frequency: 650MHz
- Benchmark duration: 2.5 minutes
- Sample interval: 30 seconds

## Output

The benchmark results are saved to `bitaxe_benchmark_results.json`, containing:
- Complete test results for all combinations
- Top 5 performing configurations ranked by hashrate
- For each configuration:
  - Average hashrate
  - Temperature readings
  - Power efficiency metrics (J/TH)
  - Voltage/frequency combinations tested

## Safety Features

- Automatic temperature monitoring with safety cutoff (66°C chip temp)
- Voltage regulator (VR) temperature monitoring with safety cutoff (90°C)
- Graceful shutdown on interruption (Ctrl+C)
- Automatic reset to best performing settings after benchmarking
- Input validation for safe voltage and frequency ranges
- Hashrate validation to ensure stability

## Benchmarking Process

The tool follows this process:
1. Starts with user-specified or default voltage/frequency
2. always find stable temp before starting benchmark sample
3. Uses PSO algorithom with a Cost function to optimise a numeric goal
4. Records and ranks all successful configurations
5. Automatically applies the best performing stable settings

## Todo 
* add Shufps test struct server for the same jobs and allowing lower pool diff reducing benchmarking time and hashrate variance


## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.





## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

## Disclaimer

Please use this tool responsibly. Overclocking and voltage modifications can potentially damage your hardware if not done carefully. Always ensure proper cooling and monitor your device during benchmarking.