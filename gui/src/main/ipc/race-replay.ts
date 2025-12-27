import { ipcMain } from 'electron'
import { spawn } from 'child_process'
import path from 'path'

export function registerRaceReplayIPC(venvPython: string): void {
  const pythonScript = path.join(__dirname, '../../../main.py')

  ipcMain.on('run-race-replay', (event, args: { year: number; round: number }) => {
    const pythonArgs = [pythonScript, '--year', String(args.year), '--round', String(args.round)]

    const python = spawn(venvPython, pythonArgs, {
      cwd: path.dirname(pythonScript)
    })

    python.stdout.on('data', (data) => {
      event.sender.send('python-output', data.toString())
    })

    python.stderr.on('data', (data) => {
      event.sender.send('python-output', `ERROR: ${data.toString()}`)
    })

    python.on('close', (code) => {
      event.sender.send('python-output', `Python script exited with code ${code}`)
    })
  })
}
