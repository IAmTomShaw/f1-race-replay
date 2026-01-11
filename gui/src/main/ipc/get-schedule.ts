import { ipcMain } from 'electron'
import { spawn } from 'child_process'
import path from 'path'
import fs from 'fs/promises'

const pythonScript = path.join(__dirname, '../../python-backend/get-schedule.py')

export function registerGetScheduleIPC(venvPython: string): void {
  ipcMain.on('runGetSchedule', async (event, args: { year: number }) => {
    const filePath = path.join(__dirname, `../../../.fastf1-cache/${args.year}/schedule.json`)

    try {
      // Try reading the file asynchronously
      const scheduleJson = await fs.readFile(filePath, 'utf8')
      const schedule = JSON.parse(scheduleJson)
      // event.sender.send('python-output', 'Schedule loaded from cache.')
      event.sender.send('read-data', schedule)
    } catch (err) {
      const e = err as NodeJS.ErrnoException
      if (e && e.code === 'ENOENT') {
        const pythonArgs = [pythonScript, '--year', String(args.year)]
        const python = spawn(venvPython, pythonArgs, { cwd: path.dirname(pythonScript) })

        python.stdout.on('data', (data) => {
          event.sender.send('python-output', data.toString())
        })

        python.stderr.on('data', (data) => {
          event.sender.send('python-output', `ERROR: ${data.toString()}`)
        })

        python.on('close', async (code) => {
          event.sender.send('python-output', `Python script exited with code ${code}`)

          // Try reading the file again **after Python script finishes**
          try {
            const scheduleJson = await fs.readFile(filePath, 'utf8')
            const schedule = JSON.parse(scheduleJson)
            // event.sender.send('python-output', 'Schedule loaded after Python script.')
            event.sender.send('read-data', schedule)
          } catch (readErr) {
            event.sender.send('python-output', `Failed to read schedule: ${readErr}`)
          }
        })
      } else {
        console.error('Error reading the file:', err)
        event.sender.send('python-output', `Error reading schedule: ${err}`)
      }
    }
  })
}
