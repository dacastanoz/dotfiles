function ssh --wraps ssh --description 'Hide the local tmux while in a remote session'
    if not set -q TMUX
        command ssh $argv
        return $status
    end

    # The remote host runs its own tmux. Hide this bar and pass every key through,
    # so only the remote one is visible and it receives the prefix directly.
    command tmux set-option status off
    command tmux set-option prefix None
    command tmux set-option key-table off

    command ssh $argv
    set -l ssh_status $status

    command tmux set-option -u status
    command tmux set-option -u prefix
    command tmux set-option -u key-table
    return $ssh_status
end
