function ssh --wraps ssh --description 'Hide the local tmux while in a remote session'
    if not set -q TMUX
        command ssh $argv
        return $status
    end

    # The remote host runs its own tmux. Hide this bar and free the prefix, so only
    # the remote one is visible and it receives the prefix directly. Keep the root key
    # table: its mouse bindings are what forward the mouse to the remote tmux.
    command tmux set-option status off
    command tmux set-option prefix None

    command ssh $argv
    set -l ssh_status $status

    command tmux set-option -u status
    command tmux set-option -u prefix
    return $ssh_status
end
