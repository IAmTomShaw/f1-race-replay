import { useNavigate } from 'react-router-dom'

interface YearCardProps {
  year: number
}

export default function YearCard({ year }: YearCardProps): React.ReactElement {
  const navigate = useNavigate()

  const handleClick = (): void => {
    // Navigate to the dynamic route
    navigate(`/years/${year}`)
  }

  return (
    <button className="card year" onClick={() => handleClick()}>
      <p className="text-center text-2xl font-bold">{year}</p>
    </button>
  )
}
