# vcv-panel-gen

A generator for VCV Rack / MetaModule front-panel SVGs, built to be driven by a coding agent. You describe the panel you want in plain language; the agent writes a small spec file; the tool turns that spec into a finished, valid panel. It does the mechanical work — grid arithmetic, text rendering, validation — but it won't do the design for you: layout taste comes from you and the agent, not from the scripts.

## What it does

- Lays out a panel from a spec of knobs, jacks, switches, buttons, lights, and screens, on grids or at exact positions.
- Writes the hidden components layer that VCV's `helper.py` reads, so the panel plugs straight into a Rack module's source.
- Bakes all text to vector paths, so no font dependency ships with the panel — it renders identically on every machine.
- Validates every build: anything off the panel edge is an error; overlapping elements are warnings you can review and deliberately accept.
- Generates a browser preview with real VCV component art, so you can judge the panel as it will actually look in Rack.
- Produces MetaModule-ready output: the same SVG exports to a faceplate PNG, and a sync tool keeps a MetaModule module's control positions matched to the panel.
- Takes accurately-cropped screenshots of a built module from Rack — either in its default state (headless) or live within a patch — cropping by matching the module's own art, so the crop never drifts.

## How to use it

Point your coding agent at this repo (or at the `vcv-panel` skill, if installed). Tell it which module the panel is for and what you want; the agent reads the module's source for the real control names, writes the spec, and iterates with you.

- The spec and the generated SVG live in your module's repo, not here — the tool refuses to write output into its own checkout.
- Give feedback in plain language ("more space between the knob rows", "make the output jacks a stereo pair", "the title feels cramped"). The agent translates that into spec changes and regenerates.
- Judge the panel in the browser preview, never from the raw SVG — the raw file hides its components layer and shows only background and labels.
- Don't hand-edit the generated SVG. Every change goes through the spec, so the panel can always be regenerated.

## Things you can ask for

- A specific width in HP.
- Controls arranged in grids, rows, and columns — or anything placed anywhere; the grid is a convenience, not a rule.
- Multiple independent grids on one panel.
- Big hero knobs.
- Stereo input or output pairs.
- A separate title font, or a logo wordmark instead of a text title.
- Uppercase, lowercase, or title-case lettering.
- Background and text colors.
- Translucent tinted zones that group related controls.
- Screens and displays.
- Value labels ringing a stepped knob.
- Decorative SVG glyphs — waveform icons, tick marks, arrows.
- A connector bar tying a knob to its CV jack.
- Deliberate overlaps, accepted by name once you've decided they're fine.
- Nudging any single element a fraction of a millimeter.

## Personal defaults

Tell your agent about your standing preferences — background color, fonts, lettering case, screw style — and it will save them to `~/.config/vcv-panel-gen/theme.yaml`, where every future panel picks them up automatically. A single panel can still override any of them in its own spec.

The screenshot tool has its own personal default: set `output_dir` in `~/.config/vcv-panel-gen/screenshot.yaml` to always save shots to a folder of your choosing (otherwise they land on the Desktop).

## For agents

The complete reference — spec grammar, CLI, validation rules, the SVG contract, MetaModule sync — is [AGENTS.md](AGENTS.md). Layout judgment and workflow recipes live in the companion skill, [skills/vcv-panel/SKILL.md](skills/vcv-panel/SKILL.md).

## License

The tool's own code is under the MIT `LICENSE`. The bundled font in `fonts/DejaVuSans.ttf` is DejaVu Sans, distributed under its own permissive license (see `fonts/DejaVuSans-LICENSE.txt`); that license covers the font only, not this tool.
