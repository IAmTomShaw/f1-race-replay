import { useRoutes } from 'react-router-dom'
// @ts-ignore: generated routes module
import routes from '~react-pages'
import Footer from './components/footer'

export default function App(): React.ReactElement {
  return (
    <>
      <main>{useRoutes(routes)}</main>
      <Footer />
    </>
  )
}
