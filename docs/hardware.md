# Building the LED board: a guided project

By the end of this project you'll have a 128×64 LED board on your wall that shows live subway arrivals, plugged into an ordinary outlet. Along the way you'll learn the handful of electrical ideas that every hobby electronics project uses. No previous experience is assumed, and no soldering is required.

Here's how I'll teach it. Each new part gets three short answers: **what it is**, **what it does**, and **why we're using it**. Each new idea gets a short explanation right before you need it. Boxes marked **🛡 Safety** explain the *reason* behind a rule, because rules are easier to follow once you know why they exist. A few **Quick check** questions let you test yourself. The answers are at the bottom.

**Plan for:** about $200–250 in parts and one or two evenings.

---

## Part 1: The big picture

Before touching any parts, let's look at the whole system. Engineers break a project into **subsystems**, which are groups of parts that each do one job. Ours has three:

```
                ┌──────────────────────────── POWER ──────────────────────────────┐
 Wall outlet ── Power strip ──┬── Pi power supply (5 V, 3 A) ──► Raspberry Pi
 (120 V AC)                   │
                              └── Panel power supply (5 V, 10 A) ──► both LED panels
                └─────────────────────────────────────────────────────────────────┘

                ┌──────────────────── BRAIN ───────────────────┐   ┌──── DISPLAY ────┐
                  Wi-Fi ──► Raspberry Pi ──► Matrix Bonnet ──────ribbon──► panel 1 ──ribbon──► panel 2
                  (MTA data)  (runs our Python)   (translator)              (left half)         (right half)
                └──────────────────────────────────────────────┘   └─────────────────┘
```

1. **The brain** fetches train times over Wi-Fi, runs this project's Python code, and decides what every pixel should look like. It's the Raspberry Pi plus a small adapter board.
2. **The display** is the two LED panels. They have no idea what a train is. They light whichever LEDs they're told to, very quickly, over and over.
3. **Power** turns the electricity from your wall into what each part needs.

Notice that **data** (information: which LEDs to light) and **power** (energy: what actually lights them) travel on separate wires. Keeping those two ideas apart is the key to understanding this build. When something goes wrong later, the first question will be "is this a data problem or a power problem?"

---

## Part 2: Electricity in ten minutes

You need four ideas. A useful comparison is water flowing through a pipe.

### Voltage (volts, V): the push

Voltage is how hard electricity is being pushed, like water pressure. Your wall outlet pushes at **120 V**. Everything we build runs at **5 V**.

### Current (amps, A): the flow

Current is how much electricity actually flows, like gallons per minute. A part *draws* the current it needs. A power supply rated "10 A" can deliver *up to* 10 A. It doesn't force 10 A into anything.

### Power (watts, W): the work done

**Power = voltage × current.** A 5 V supply delivering 2 A is supplying 10 W. Watts are what turn into light, and also into **heat**, which matters a lot for safety.

### AC vs DC

Your wall outlet gives **AC** (alternating current): the push flips direction 60 times a second. That's good for sending power across a city, but electronics need **DC** (direct current): a steady push in one direction. A **power supply** converts wall AC into steady low-voltage DC. That's its whole job.

### Circuits, shorts and heat

Electricity flows only in a **loop**: out of the supply's **+** terminal, through the device, and back into the **−** terminal (also called **GND**, ground). The device in the middle **resists** the flow, and that resistance is what limits the current.

A **short circuit** happens when + and − touch directly with nothing in between, for example a stray wire strand bridging two screws. Nothing limits the current, so it rushes through at whatever the supply can deliver, and the wire heats up. Wires also heat up when they're too thin for the current they carry, or when a connection is loose: a loose screw has a tiny contact area, and squeezing current through it makes heat.

> **🛡 Safety: why 5 V is safe to touch but still needs care.** Your skin has high resistance, so 5 V can't push a meaningful current through your body. You won't get shocked by anything on the 5 V side of this project. **120 V can**, which is why this design never has you touch 120 V wiring: the power supplies are sealed and you just plug them in. The real hazard at 5 V is **heat** from shorts and loose connections, which can melt insulation or start a fire. Almost every safety rule in this guide is about preventing shorts and loose connections.

### Polarity

DC has a direction, so **+ and − matter**. The convention is **red = +** and **black = −**. Connecting them backwards (*reverse polarity*) can destroy electronics instantly.

> **Quick check 1:** A panel draws 2 A at 5 V. How many watts is that? Would a 5 V, 10 A supply force 10 A into it?

---

## Part 3: Meet the components

### The Raspberry Pi 4: the brain

**What it is.** A complete computer the size of a credit card. It has a processor, memory, Wi-Fi and USB, and it runs Linux from a microSD card.

**What it does here.** It runs this project's Python code exactly as your PC does: it downloads the MTA's live feeds, works out arrival times, draws each frame of the board as an image, and sends that image to the panels about a hundred times a second.

**Why this one.** Our code is Python and needs Wi-Fi and a real operating system, so a full computer is the easiest fit. You might hear about **microcontrollers** (like Arduino or ESP32). Those are much simpler chips that run one small program with no operating system. They can drive LED panels too, but we'd have to rewrite the whole project for them. Among Pis, the **Pi 4** is the best supported by the LED library we use. The newer Pi 5 changed how its pins work internally, and the library doesn't officially support it yet. 2 GB of memory is plenty.

**New idea: GPIO pins.** Along one edge of the Pi is a row of 40 metal pins called the **GPIO header** (General Purpose Input/Output). Software can switch each pin on (3.3 V) or off (0 V) millions of times per second. That's how a computer talks to hardware: by toggling pins in a pattern. Our adapter board plugs onto these pins.

### The microSD card: the hard drive

**What it is / does.** It holds the operating system (Raspberry Pi OS), our code, and everything else the Pi stores. **Why:** the Pi has no built-in storage. Get a name brand (SanDisk, Samsung), 16–32 GB. Cheap cards fail more often.

### The Pi's power supply

**What it is.** The official Raspberry Pi USB-C supply: 5.1 V, up to 3 A (15 W).

**Why the official one.** When the Pi suddenly works harder, its current draw jumps. A weak supply's voltage *sags* for a moment, and the Pi may crash or corrupt its SD card. Many phone chargers do this. The official supply is built to hold steady, and it runs slightly above 5 V on purpose to make up for the small voltage loss in the cable.

### The LED panels: the display

**What they are.** Each panel is a circuit board covered in a grid of 64 × 64 = 4,096 tiny **RGB LEDs**. Each LED is really three, one red, one green, one blue, packed together. Mixing them makes any color: red + green = amber, all three = white. Two panels side by side make our 128 × 64 display.

**Pitch** is the distance between LED centers, in millimeters. P2.5 means 2.5 mm apart, so a 64-pixel panel is 160 mm (6.3 in) wide. Bigger pitch means a bigger board with the same number of pixels: **P2.5** gives a 32 × 16 cm board for a desk or shelf, and **P3** gives a 38 × 19 cm board for a wall. Both panels must be the same model and pitch.

**How a panel actually works (the clever part).** You might expect 4,096 LEDs to need 4,096 wires. They don't, because the panel uses two tricks:

1. **Scanning.** Only **two rows** are lit at any instant: one in the top half and the matching one in the bottom half. The panel lights rows 1 and 33, then 2 and 34, and so on through all 32 pairs, hundreds of times per second. Your eyes blend the rapid flashes into a steady image (this is called *persistence of vision*). So the panel only needs to know about 2 rows at a time, not 64.
2. **Shift registers.** Each row's color data is sent **one pixel at a time** down a few wires, like people passing buckets down a line. A **clock** signal says "pass it along one spot", and a **latch** signal says "everyone, show what you're holding". The chips that do this are called shift registers.

**Address lines, and why "E" matters.** To pick which of the 32 row-pairs is lit, the panel uses **address lines** named A, B, C, D, E. Each line is a yes/no, and five yes/no lines can count to 2⁵ = **32**. Panels that are only 32 pixels tall need just 16 row-pairs, which is 4 lines (A–D). Our 64-tall panels need the fifth line, **E**. If E isn't connected, the panel can only reach half its rows, and you get a doubled or half-blank picture. Remember this; it comes up again soon.

**Chaining.** Each panel has an **IN** and an **OUT** connector. Data that "falls off the end" of panel 1's shift registers comes out of OUT and flows into panel 2. So the Pi sees one long 128-pixel-wide display. That's why the software setting is called `chain`.

**Why Adafruit's panels.** The connector standard is called **HUB75**, but the chips on cheap marketplace panels vary, and some need special settings. Adafruit's 64×64 panels are known to work with our adapter and library, which removes one source of mystery on your first build.

> Can't find two matching panels, or want no seam down the middle? A **single 128×64 panel** works too. The picture is the same, with one ribbon and one power plug. Run the software with `--module 128x64 --chain 1`. The catch: those panels more often use unusual driver chips, so pick a listing that says it works with "rpi-rgb-led-matrix".

### The Adafruit Triple LED Matrix Bonnet: the translator

**What it is.** A small board (#6358, about $10) that plugs onto the Pi's 40 GPIO pins and has HUB75 connectors for ribbon cables. ("Bonnet" and "HAT" are Raspberry Pi names for add-on boards that sit on top.)

**What it does.** Two jobs:

1. **Routing.** It connects the right Pi pins to the right HUB75 wires (colors, clock, latch, address lines).
2. **Level shifting.** The Pi's pins speak **3.3 V logic**: "on" means 3.3 V. The panels expect **5 V logic**. A 3.3 V signal is right at the edge of what a 5 V chip counts as "on", which leads to random sparkles and glitches. The Bonnet's **level shifter** chips turn each 3.3 V signal into a clean 5 V one.

**Why this one.** It has a **switch** that connects the E address line, so you don't need soldering. It's called "Triple" because it can drive three separate chains of panels. We'll use only the first one.

**What it doesn't do: power.** The Bonnet only passes *data*. Panel power goes from the panel supply straight to the panels, which is the data/power split from Part 1 again.

> **The other option: the original RGB Matrix Bonnet (#3211).** It has a built-in power jack and screw terminal for the panels, a green "power good" light, and **reverse-polarity protection**: a circuit that blocks current if + and − are swapped, so a wiring mistake doesn't destroy anything. The catch is that its E line needs **one blob of solder** to connect. If you have access to a soldering iron (or a friend or makerspace), it's slightly more beginner-proof on the power side. If you use it, follow Adafruit's guide for the E jumper, plug the panel supply into its jack, and run the software with `--gpio-mapping adafruit-hat` (the default) instead of `regular`.

### The ribbon cables: the data highway

**What they are.** Flat 16-wire cables with **IDC** connectors (Insulation Displacement Connectors: sharp metal forks that bite through the insulation onto each wire). HUB75 uses 16 wires: 6 for color (red, green and blue for the top half and the bottom half), 5 address lines, clock, latch, an "output enable" that blanks the LEDs between rows, and ground.

**Why the connectors are keyed.** A notch makes them fit only one way, so you can't plug in a cable flipped. Panels usually include one ribbon each, and you need two: Bonnet → panel 1, and panel 1 → panel 2.

### The panel power supply: the muscle

**What it is.** A sealed "brick", like a laptop charger, that plugs into the wall and outputs **5 V DC, up to 10 A (50 W)** through a round **barrel plug** (e.g. Adafruit #658).

**Why such a big one?** Let's actually calculate it. This is the most important engineering decision in the project, and it's done in [Part 4](#part-4-power-planning-doing-the-math).

**Why a sealed brick.** Inside is the circuitry that converts 120 V AC to 5 V DC, safely enclosed. A properly certified supply also has built-in protection: if something draws too much current or shorts out, the supply shuts itself off instead of overheating.

> **🛡 Safety: what to buy and what to avoid.**
> - **Look for a UL, ETL or CSA mark** on the label. Those are independent safety testing labs. No mark means nobody checked that the protections inside actually work.
> - **Avoid "open frame" supplies.** They're the silver metal boxes with a row of screw terminals marked L / N / ⏚ (like the Mean Well LRS series). LED tutorials use them a lot, but you'd have to screw bare 120 V wall wiring into them yourself. That's a real shock and fire risk for a beginner. A brick does the same job with the dangerous part sealed away.
> - **Read the output line.** It must say `5V` (not 9 V or 12 V, even if the plug fits). Feeding 12 V into 5 V panels destroys them.

### The barrel-jack adapter: getting power out of the plug

**What it is.** A small female socket that the brick's round plug pushes into, with two **screw terminals** marked + and −.

**What it does / why.** The brick has a round plug, but the panel power cables end in bare wire or metal forks. The adapter connects the two with just a screwdriver. A **screw terminal** is a little metal clamp: you put a wire under it and tighten the screw.

Brick plugs are usually **center-positive**: the inner pin is +, the outer sleeve is −. The adapter's markings take care of this for you, but it's why the label has a little ⊖–◖●–⊕ diagram.

Pick an adapter that matches the brick's plug size (usually **5.5 × 2.1 mm**) and lists a current rating of **5 A or more**.

### The panel power cable

Each panel usually comes with a cable that has a **4-pin plug** (two + pins and two − pins, to share the current) and red and black wires at the other end. Many cables have two plugs, enough for two panels. The red and black ends go into the adapter's screw terminals.

### Power strip with a switch

**Why.** Two supplies would mean two wall plugs. A power strip turns them into **one plug in the wall** and gives you a single **off switch** for the whole board, which is very handy while building and testing. A surge-protected strip also guards against voltage spikes.

### Multimeter (strongly recommended)

**What it is.** A handheld meter that measures voltage, current and resistance. A $15–25 one is plenty.

**Why.** It lets you *check* instead of *hope*. Before connecting power to the panels, you'll measure the wires to confirm "+5 V, the right way round". That matters more here because the Triple Bonnet setup has no reverse-polarity protection.

### Shopping list

| Part | Why (one line) | ~Price |
| --- | --- | --- |
| Raspberry Pi 4 Model B, 2 GB | The brain: runs our Python code | $45 |
| Official Raspberry Pi USB-C power supply (15 W) | Steady power for the Pi | $8 |
| microSD card, 16–32 GB, name brand | Storage for the OS and code | $10 |
| Adafruit Triple LED Matrix Bonnet (#6358) | Translates Pi pins to HUB75 at 5 V, with an E switch (no solder) | $10 |
| 2× Adafruit 64×64 RGB LED panels, same pitch (P2.5 or P3) | The display; usually include a ribbon and a power cable | $40–60 each |
| Spare 16-pin HUB75 ribbon cable, if needed | You need two in total | $3 |
| 5 V 10 A power brick, UL/ETL listed, 5.5 × 2.1 mm plug (e.g. Adafruit #658) | Power for the panels | $25–30 |
| Female 5.5 × 2.1 mm barrel-jack-to-screw-terminal adapter, rated ≥ 5 A | Connects the brick to the panel cable without solder | $3–5 |
| Power strip with an on/off switch | One wall plug, one off switch | $10–15 |
| Multimeter | Check voltage and polarity before connecting | $15–25 |
| Small screwdriver set | For the screw terminals | — |
| Stick-on heatsinks for Pi 4 | Help the Pi's chips shed heat (most cases won't fit with the Bonnet) | $5 |
| Optional: smoked/tinted acrylic + frame | Hides the LED grid, so it looks like a real MTA countdown clock | $15–30 |

---

## Part 4: Power planning (doing the math)

This is a real engineering calculation, the same kind used for professional LED signs. We'll work through it together.

**Step 1: How much does one LED draw?** Each color in an LED draws about **20 mA** (0.02 A) at full brightness.

**Step 2: How many LEDs are on at once?** Remember scanning: each panel lights only **2 rows** at a time. Each row is 64 pixels, and each pixel has 3 colors. So at full white:

```
2 rows × 64 pixels × 3 colors × 0.02 A = 7.7 A per panel
2 panels × 7.7 A                       ≈ 15 A worst case
```

**Step 3: Wait, that's more than our 10 A supply.** It is, and this is where engineering judgment comes in. That 15 A is for **every LED on full white at 100% brightness**, which our board never does. Real panels also measure a bit below the theoretical figure. Let's estimate what *our* board actually draws:

- The board is mostly **black background** with colored text, so about **10–15%** of the LEDs are lit.
- The software caps brightness at **60%** by default.

```
15 A × 0.15 lit × 0.60 brightness ≈ 1.4 A typical
```

So a typical draw is **under 2 A**. The 10 A supply runs at a small fraction of its capacity, which means it stays cool and lasts a long time. Running a supply near its maximum all day is like redlining a car engine.

**Step 4: What if something tries to draw too much?** Say a bug turns the whole screen white. The certified supply's **overload protection** notices that more than 10 A is being demanded and shuts itself off or reduces its output. Nothing overheats. That safety net is part of why we insist on a certified brick.

**The design decisions this gives us:**

1. A **10 A** supply: lots of headroom for normal use.
2. Keep `--brightness` **at 60 or below**. Indoors, 30–50 usually looks better anyway.
3. Don't run full-white test patterns at full brightness. When using the library's demos, add `--led-brightness=50`.
4. Adding panels later means redoing this math.

> **Quick check 2:** If you added a third 64×64 panel and turned the whole screen white at 100%, roughly how much current would that demand? What would the supply do?

---

## Part 5: The build

> **🛡 Safety: the build rules, and why they exist.**
> 1. **The power strip stays unplugged** until Part 6. Plugging in or unplugging cables while powered can send a jolt through the chips before all the pins make contact. It's also how accidental shorts happen.
> 2. **Work on a non-conductive surface**: wood, cardboard or a cloth, never a metal table. Metal under a circuit board can bridge pins on the back and short them.
> 3. **No loose strands.** A single stray copper strand across two terminals is a short circuit.
> 4. **Tighten and tug.** Loose connections heat up (Part 2). After every screw terminal, give the wire a firm tug.

### Step 1: Prepare the Pi

1. Stick the heatsinks onto the Pi's largest chips (the processor in the middle is the main one).
   *Why:* every chip turns some power into heat. A heatsink's metal fins spread that heat out so the Pi doesn't slow itself down to cool off.
2. Line the Bonnet's 40-pin socket up over the Pi's 40 pins, so the Bonnet sits **over** the Pi rather than hanging off the side. Press straight down evenly until it's fully seated, with no pins left showing at either end.
   *Why:* if it's shifted by one pin, every signal lands on the wrong wire.

### Step 2: Set the E switch

Find the small switch on the Bonnet for **Address E**. It selects whether E goes to **pin 4 or pin 8** of the HUB75 connector. Adafruit's 64×64 panels use **pin 8**, so set it to 8. (Panels from other sellers might use 4; their listing or datasheet will say.)

*What you just did:* you connected the fifth address line, so the panels can reach all 32 row-pairs. If you skip this, you'll see the half-blank or doubled picture described in Part 3.

### Step 3: Arrange the panels and connect data

1. Lay both panels **face down** on a soft cloth, side by side, to form a 128 × 64 rectangle.
2. On the back of each panel, find the two 16-pin connectors marked **IN** (or JIN) and **OUT** (JOUT), and the printed **arrows** that show data flow. Turn the panels so the arrows on both point the same way.
3. **Ribbon A:** Bonnet output **1** (the first chain; check the label on the board) → panel 1 **IN**.
4. **Ribbon B:** panel 1 **OUT** → panel 2 **IN**.

*Why the direction matters:* data shifts *through* the panels like a conveyor belt. Feeding a panel through its OUT is like pouring water into the drain end of a pipe.

If the picture later shows up with the halves swapped or upside down, just rearrange or rotate the panels. Swapping data cables (with power off) can never damage anything.

### Step 4: Wire the panel power

1. Push one 4-pin plug of the panel power cable into each panel's power socket. It only fits one way. Look at the panel's circuit board next to the socket for **VCC / +5V** and **GND** labels, and confirm the **red** wires line up with VCC.
2. Take the red and black wires at the other end. If they end in metal forks or rings that won't fit the adapter, cut them off with wire cutters, strip about 6 mm (¼ in) of insulation, and twist the copper strands tight.
3. Loosen the barrel adapter's screws. **Red → +** and **black → −**. Tighten firmly. No bare copper should show outside the terminal.
4. **Tug test** both wires.
5. **Don't plug the brick in yet.**

*What you've built:* a complete power loop. Current flows from the brick's + through the red wire, through the LEDs, back through the black wire, and into the brick's −.

**Where does ground meet?** The panels get *power* from the brick, but *data* from the Pi. For a 5 V signal to mean anything, both sides have to agree on what 0 V is, so the ribbon cable includes **ground** wires that tie the Pi's ground to the panels' ground. This is called a **common ground**, and the ribbon handles it for you. It's a good concept to remember: whenever two separately powered devices talk to each other, they need a shared ground.

---

## Part 6: First power-on, measure before you trust

Engineers don't power up a new circuit and hope. They check step by step, starting with the cheapest thing to get wrong.

### Checklist

If any answer is "no", stop and fix it.

- [ ] The brick's label says **5V** output and has a UL/ETL/CSA mark.
- [ ] Red → + and black → − at the adapter, and red goes to VCC on the panels.
- [ ] No stray strands, screws or tools on or under any board.
- [ ] The E switch is set to 8.
- [ ] The Bonnet is fully seated, and the ribbons go Bonnet → panel 1 IN, panel 1 OUT → panel 2 IN.
- [ ] Everything sits on a non-conductive surface.

### Measure the voltage (your first multimeter reading)

1. **Unplug the power cable's 4-pin plugs from both panels**, leaving the cable attached to the adapter. We're testing the supply before trusting it with the panels.
2. Set the multimeter dial to **DC volts** (marked **V⎓** or **DCV**, choose the 20 V range if it asks). The black probe goes in **COM** and the red probe in **V**.
3. Plug the brick into the power strip, plug its barrel plug into the adapter, and switch the strip on.
4. Touch the red probe to a red-wire pin on the 4-pin plug and the black probe to a black-wire pin.
   - A reading of about **+5.0 V** (anything from 4.9 to 5.3) means correct polarity and the right voltage. 🎉
   - About **−5 V** (a minus sign) means **red and black are swapped**. Switch off and swap them at the adapter.
   - A reading of 9 or 12 means you have the wrong brick.
   - 0 means no power: check the plug, the strip switch and the adapter screws.
5. Switch the strip **off**. Plug the 4-pin plugs back into the panels.

*Why the minus sign is useful:* a multimeter shows the red probe's voltage relative to the black probe. A negative number means "the red probe is on the lower side", so your polarity is backwards. You've just caught a wiring mistake with zero risk.

### Power up for real

1. Plug the Pi's USB-C supply into the Pi and into the strip.
2. Switch the strip on. The Pi's red LED should light. The panels will stay dark or show random speckles, because nothing is sending them data yet. That's normal.
3. Stay nearby. If you smell burning or see smoke, or anything gets hot within seconds, **switch the strip off** and recheck the wiring.

---

## Part 7: Software setup

The hardware is done. Now let's give the brain its instructions.

### 7.1 Install the operating system

The **operating system** (OS) is the base software that manages the hardware and runs programs. Windows is one; the Pi runs **Raspberry Pi OS**, a version of Linux. We use the **Lite** edition, which has no desktop. The board doesn't need a screen, so we skip the overhead and control the Pi from your PC instead.

1. On your PC, install **Raspberry Pi Imager**.
2. Choose **Raspberry Pi 4** → **Raspberry Pi OS Lite (64-bit)** → your SD card.
3. Open the settings (gear or "Edit settings"). Set a hostname (e.g. `mtaboard`), a username and password, your **Wi-Fi name, password and country**, your **time zone (America/New_York)**, and **enable SSH**.
4. Write the card, put it in the Pi, power up, and wait about 2 minutes.
5. From your PC's terminal: `ssh <user>@mtaboard.local`

*What's SSH?* **Secure Shell** lets you type commands into the Pi's terminal from your PC over the network, as if you had a keyboard plugged into the Pi.

### 7.2 Prepare the Pi

```sh
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git python3-venv python3-dev cython3
```

`apt` is Raspberry Pi OS's app store for the command line. `sudo` means "run this as the administrator".

Next, **turn off the onboard audio**:

```sh
sudo sed -i 's/^dtparam=audio=on/dtparam=audio=off/' /boot/firmware/config.txt
grep audio /boot/firmware/config.txt     # should show dtparam=audio=off
sudo reboot
```

*Why:* the panels need perfectly timed pulses on the GPIO pins. The Pi's audio uses the same timing hardware the LED library relies on, and with both running, the panel flickers or glitches.

Optional, for smoother display: add ` isolcpus=3` to the **end of the single line** in `/boot/firmware/cmdline.txt`, then reboot. *Why:* the Pi has 4 processor cores. Linux normally shares them among all programs, so the LED loop sometimes gets interrupted, which shows up as flicker. This setting reserves core 3 for it.

### 7.3 Install the project and the LED library

```sh
git clone <this repo's URL> ~/mta_tracker
cd ~/mta_tracker
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

git clone https://github.com/hzeller/rpi-rgb-led-matrix ~/rpi-rgb-led-matrix
cd ~/rpi-rgb-led-matrix
~/mta_tracker/.venv/bin/pip install .        # installs the `rgbmatrix` Python module into the venv
make -C examples-api-use                      # builds the test demo
```

*What's happening:*
- A **venv** (virtual environment) is a private folder of Python packages for this project, so it can't conflict with anything else on the Pi.
- **rpi-rgb-led-matrix** is the open-source library that does the hard real-time work: toggling GPIO pins in exactly the right pattern to scan rows and shift in pixels, hundreds of times per second. Our Python code just hands it a finished image. On your PC, the emulator stands in for this library, which is why the same code works on both.

### 7.4 Test the hardware with the library's demo

Test one layer at a time. Before running our code, confirm the hardware works with the library's own demo:

```sh
cd ~/rpi-rgb-led-matrix/examples-api-use
sudo ./demo -D0 --led-rows=64 --led-cols=64 --led-chain=2 \
  --led-gpio-mapping=regular --led-slowdown-gpio=4 --led-brightness=50
```

What each setting tells the library:
- `rows=64 cols=64`: the size of *one* panel.
- `chain=2`: two panels connected in a chain.
- `gpio-mapping=regular`: which Pi pins the Bonnet uses for each HUB75 signal. The Triple Bonnet uses the standard pinout, which the library calls `regular`.
- `slowdown-gpio=4`: the Pi 4 can toggle pins faster than the panel's shift registers can keep up with, so this deliberately slows it down.
- `brightness=50`: our power-budget rule from Part 4.

You should see a spinning colored square across both panels. Press Ctrl+C to stop. If it doesn't appear, go to [Part 9](#part-9-troubleshooting-like-an-engineer) before moving on. There's no point debugging our code until the hardware is known to work.

### 7.5 Run the arrival board

```sh
cd ~/mta_tracker
sudo .venv/bin/python -m mta_tracker --led hardware --gpio-mapping regular
```

The station search shows up in your SSH window, and the board lights up on the panels. To start straight at a station:

```sh
sudo .venv/bin/python -m mta_tracker --led hardware --gpio-mapping regular "times sq" --brightness 40
```

*Why `sudo`?* Toggling GPIO pins this fast requires direct access to the hardware, and only the administrator (root) has that. As soon as the library has set up the hardware, it switches itself to an ordinary low-permission user called `daemon`. That's good security practice: a program should hold admin powers only for as long as it needs them.

### 7.6 Start automatically at boot

**systemd** is the part of Linux that starts programs at boot and restarts them if they crash. We give it a short "service" file describing our program.

Because of the privilege drop just mentioned, the cache folder must be writable by the `daemon` user:

```sh
sudo mkdir -p /var/cache/mta_tracker
sudo chown daemon:daemon /var/cache/mta_tracker
```

Create the service file with `sudo nano /etc/systemd/system/mta-board.service`. Replace `<user>` and the station:

```ini
[Unit]
Description=MTA arrival board
Wants=network-online.target
After=network-online.target time-sync.target

[Service]
WorkingDirectory=/home/<user>/mta_tracker
Environment=MTA_TRACKER_CACHE=/var/cache/mta_tracker
ExecStart=/home/<user>/mta_tracker/.venv/bin/python -m mta_tracker --led hardware --gpio-mapping regular "times sq" --brightness 40
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

`After=network-online.target time-sync.target` means "wait for Wi-Fi and the correct time before starting". The Pi has no clock battery, so it gets the time from the internet at boot.

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now mta-board
journalctl -u mta-board -f        # watch the logs; Ctrl+C to stop watching
```

To change station, edit the `ExecStart` line, then run `sudo systemctl daemon-reload && sudo systemctl restart mta-board`.

**Turning it off properly:** run `sudo shutdown now` over SSH, wait about 20 seconds until the Pi's green LED stops blinking, then switch off the strip. *Why:* Linux saves files in memory and writes them to the SD card later. Cutting power suddenly can catch it mid-write and corrupt the card.

---

## Part 8: Mounting it for the long run

- **Airflow.** Most panels have magnetic feet or M3 screw holes on the back. Build a simple frame (wood or 3D-printed) and leave **at least 2–3 cm behind the panels** so warm air can rise away. Heat that can't escape builds up.
- **Strain relief.** Fasten the Pi, Bonnet, adapter and cables to the frame with zip ties or adhesive clips, so nothing hangs by a cable. A wire that gets pulled every time someone bumps the frame will eventually loosen at a screw terminal, and loose connections are where heat starts.
- **Keep the brick outside the frame.** Put it on a shelf or the floor, in open air, not taped behind the panels or under a rug.
- **The first few days:** run it while you're home. After about 30 minutes, feel the brick, the barrel adapter and the panel cable. Warm is normal. Too hot to hold a finger on means unplug and investigate: usually a loose screw terminal, or brightness set too high.
- A **smoked acrylic** front panel hides the LED grid (like the real MTA clocks) and protects the LEDs from fingers and dust.

---

## Part 9: Troubleshooting like an engineer

When something's wrong, don't change things at random. Ask **which subsystem** is failing, then test that one.

**Power problems** (nothing lights, or things get hot):

| Symptom | Reasoning / fix |
| --- | --- |
| Panels completely dark, Pi works | Measure the panel cable with the multimeter (Part 6). No 5 V means check the brick, the strip switch and the adapter screws. |
| Pi keeps rebooting; `dmesg` mentions "under-voltage" | The Pi's supply is sagging under load. Use the official supply. |
| Brick, adapter or cable gets **hot** | **Unplug.** Look for a loose screw terminal (it heats at the contact point) or brightness set too high. |

**Data problems** (lit, but wrong):

| Symptom | Reasoning / fix |
| --- | --- |
| Dark, but 5 V measures fine | The data isn't arriving. Check that the ribbon goes into **IN** (not OUT), that it's in Bonnet output 1, and that `--gpio-mapping regular` is set. |
| Only the top half works, or the image repeats in both halves | The **E** address line isn't reaching the panel. Check the E switch; try the other position (4 instead of 8). |
| Halves swapped, or the picture is upside down | Data reaches the panels in a different order than you laid them out. Swap or rotate the panels. |
| Sparkles, garbled or random pixels | The signal is too fast or noisy. Raise the slowdown (`--gpio-slowdown 5`), reseat the ribbons, or use shorter ribbons. |
| Marketplace panels stay blank or freeze | They may use a different driver chip (e.g. FM6126A) that needs a startup command. Try the demo with `--led-panel-type=FM6126A`. If that fixes it, the project needs a small option added in `display/matrix.py`. |
| Faint flicker | The LED loop is getting interrupted. Add `isolcpus=3` (Part 7.2) and confirm audio is off. |

**Software problems:**

| Symptom | Reasoning / fix |
| --- | --- |
| Wrong time on the board | Check the time zone with `timedatectl` and that the Pi is online. |
| `PermissionError` on the cache when run by systemd | The privilege drop: the cache folder must be owned by `daemon` (Part 7.6). |

---

## What you learned

- **Voltage, current, power:** push, flow, and work done (watts = volts × amps).
- **AC vs DC**, and what a power supply does.
- **Circuits, shorts and heat**, and why loose connections are dangerous.
- **Polarity**, and checking it with a multimeter before trusting it.
- **Power budgeting:** calculating worst case and typical draw, and designing for headroom.
- **Logic levels:** why 3.3 V signals need a level shifter to drive 5 V chips.
- **How LED matrices work:** scanning rows, shift registers, address lines (2⁵ = 32) and chaining.
- **Common ground** between separately powered devices.
- **Layered testing:** supply → hardware demo → our code.

Natural next steps: add a button or a small web page for changing stations, or use the spare 8th text row for service alerts. See "Remaining work" in the [README](../README.md).

---

## Quick check answers

1. 5 V × 2 A = **10 W**. And **no**: a supply's amp rating is the maximum it *can* deliver. The panel draws only the 2 A it needs.
2. Three panels × about 7.7 A ≈ **23 A**, far over 10 A. A certified supply's overload protection would shut down or reduce its output. That's why you redo the power math (and probably buy a bigger supply) before adding panels.

## References

- Adafruit Triple LED Matrix Bonnet guide: <https://learn.adafruit.com/adafruit-triple-led-matrix-bonnet-for-raspberry-pi-with-hub75>
- Adafruit RGB Matrix Bonnet guide (the soldered alternative): <https://learn.adafruit.com/adafruit-rgb-matrix-bonnet-for-raspberry-pi>
- hzeller/rpi-rgb-led-matrix (the LED library and all `--led-*` options): <https://github.com/hzeller/rpi-rgb-led-matrix>
