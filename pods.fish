# Completions for pods — the AirPods controller (~/projects/pods).
# -f: no argument this tool takes is ever a filename.

complete -c pods -f
complete -c pods -n __fish_use_subcommand -a anc -d 'Noise cancellation'
complete -c pods -n __fish_use_subcommand -a transparency -d 'Transparency mode'
complete -c pods -n __fish_use_subcommand -a adaptive -d 'Adaptive mode'
complete -c pods -n __fish_use_subcommand -a off -d 'Noise control off'
complete -c pods -n __fish_use_subcommand -a battery -d 'Left / right / case battery'
complete -c pods -n __fish_use_subcommand -a status -d 'Connection, mode and battery'
complete -c pods -n __fish_use_subcommand -a ear -d 'Ear-detect pause: show, or on / off'
complete -c pods -n __fish_use_subcommand -a run -d 'The app itself (pods.service runs this)'
complete -c pods -n '__fish_seen_subcommand_from ear; and test (count (commandline -opc)) -eq 2' -a on -d 'Pause when a bud comes out'
complete -c pods -n '__fish_seen_subcommand_from ear; and test (count (commandline -opc)) -eq 2' -a off -d 'Never pause or resume'
