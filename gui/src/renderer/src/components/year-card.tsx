import { useNavigate } from 'react-router-dom'

interface YearCardProps {
  year: number
}

declare global {
  interface Window {
    api: {
      runPython: (args: { year: number; round: number }) => void
      onPythonOutput: (callback: (data: string) => void) => void
    }
  }
}

export default function YearCard({ year }: YearCardProps): React.ReactElement {
  const navigate = useNavigate()
  // const runPython = (year: number): void => {
  //   window.api.runPython({ year: year, round: 2 })

  //   // Optional: listen to Python output
  //   window.api.onPythonOutput((data) => {
  //     console.log(`Python Output: ${data}`)
  //   })
  // }

  const handleClick = (): void => {
    // Navigate to the dynamic route
    navigate(`/years/${year}`)
  }

  return (
    <button
      className="flex flex-col items-center justify-center border-white rounded-lg bg-black p-4 mt-5 w-24 h-24"
      onClick={() => handleClick()}
    >
      <p className="text-center text-2xl font-bold">{year}</p>
    </button>
  )
}
