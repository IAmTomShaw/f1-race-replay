import { useParams, useNavigate } from 'react-router-dom'

export default function Year(): React.ReactElement {
  const navigate = useNavigate()
  const { year } = useParams()

  const handleClick = (): void => {
    navigate('/')
  }
  return (
    <>
      <h1>Year: {year}</h1>
      <button onClick={() => handleClick()}>Back</button>
    </>
  )
}
