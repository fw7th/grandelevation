import base64
import json
import os
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv
from fastapi import Request as FastAPIRequest
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from .models import Product, Session, Users


async def get_active_categories(session: AsyncSession) -> list[str]:
    """
    Categories that actually have products right now, pulled live from
    the DB -- not the static SPEC_MODELS list. This is what the admin
    panel can create products in, and it grows/shrinks automatically as
    products are added/removed, with no code change needed.
    """
    statement = select(Product.category).distinct()
    result = await session.exec(statement)
    return sorted(result.all())


# If modifying these scopes, delete the file token.json.
# This scope allows full sending capabilities.

# Make sure it has "www." and the full "/auth/gmail.send" path
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def sync_gmail_dispatch(recipient_email: str, reset_link: str):
    """Synchronous executor block that interacts with the blocking Google SDK client."""

    load_dotenv()
    creds = None

    # Try env var first (Vercel)
    token_env = os.getenv("GMAIL_TOKEN")
    if token_env:
        creds = Credentials.from_authorized_user_info(json.loads(token_env), SCOPES)

    # Fallback to local file (dev)
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds:
        raise ValueError("No GMAIL_TOKEN env var and no token.json found.")

    # Background token refresh tracking
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        if not os.getenv("VERCEL"):
            with open("token.json", "w") as token:
                token.write(creds.to_json())

    # Initialize client
    service = build("gmail", "v1", credentials=creds)

    # Construct HTML Email structure
    message = MIMEMultipart("alternative")
    message["To"] = recipient_email
    message["Subject"] = "Reset Your Password - GrandElevationSolar"
    html_content = f"""
    <html>
    <body style="margin:0; padding:0; background-color:#FAF8F3;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#FAF8F3;">
        <tr>
          <td align="center" style="padding:48px 20px;">
            <table role="presentation" width="100%" max-width="480" cellspacing="0" cellpadding="0" border="0" style="max-width:480px; width:100%; background:#ffffff; border-radius:20px; border:1px solid rgba(10,10,10,0.08); overflow:hidden;">
              
              <!-- Header -->
              <tr>
                <td style="padding:36px 36px 24px; text-align:center; border-bottom:1px solid rgba(10,10,10,0.06);">
                  <img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAKAAAACgCAYAAACLz2ctAAA8fklEQVR4nO29d3wd1ZnH/T1T7r26ai5yl42Ne2+xwTbd1NDDOtR1gGxedikJCQlJNptNFl6WBPKuA5tNliUBliRLSUwIHYKNMQbb4F5ww022cJEl2aq3zMzz/jFzRiO527IkG/38mc+V78ydOTPnN087z3mO4gsCETEABSillHOA/TGgI1AMnA70AfoCPYCuwb4iwIh8NkUZ4AGVQDmwG9gFbAFKgE3ANqBCKZU6QBssQABRSnnHfLMnEVRrN+BEIkK6Rh0afN8DGA2MAoYDg4B+QCEQO0FNygLVwFZgXbAtBZYBnyulspE2KsDEJ7QopeQEtalVccoRMEI6L9ppIlIMTATOBibgEy//YKeJbATniz6rgz03afJ3098f7Hf1wGrgY+BDYIFSalOT+zI5BSXjKUHAQFoYRDoo+G4kcBlwPj75Ojb9Kb6EgcOTpNma22Qz2F+d1wKfAHOAN4GlWjpG7tU7FaTiSU1ALe2UUm7ku8HANcBV+JLOjvzEC7bQHmyxxh4amoy6bU0JuRh4A5iplFoe/ugUkIptpQOOCk2JJyIdgMuBm4DzgGTkcE1OTbqTAVHJbEa+zwLzgOeBvyqldsGBX8STBSdLhwDhgyaiZvsDXwNuBAZEDnXx7+1AnurJCA+flFEybgP+BDyllFoNJycRTwoCHkDijQX+EZhGg113Mkq6Y4G+T03GOuAV4L+UUvNg/xe1LaNNd5Q2uCPEmwh8B9/GiweHnWrS7kih1bQZ+f8bwH8opWZDaCO2aWelzRJQRMwI8YYB9wHTASs4xOXUl3ZHgqjzop/Fn4BHlVKfQONn2dbQ5jovqj5EpAu+xLsHyA0OaSfewRF9Ng7wW+BnSqmtTbVJW0Gb6sQmUu8W4KdA/2C3g69u2lSb2yhcGlTzTuBh4FfBS92m1HKb6MxA6olSSkRkBPAIfgAZ2ol3rBB8ImqT5QPgB0qpj6DtqOVW71QRsXRygIjcC/wrvmfbrmqbB1FnJQP8DPh3pVQ6+uxbC63WuVGbREQGAL8GLgp2R1VIO5oH0Wf6CXCnUmpRVPu0RqNaJXQhIoZSSgLyXY8f3b8I/yE1Dbi2o3lg0qCWJwDvichdSikvMH1ahQstLgG17RHk3z2M7+VCu9RrSUSf9bPAN5VS+1pDJbcoAfUNBqlRz+JnqbTbeq2DqJOyDLhFKbW6pUnYYp0eId8U4A/42cYODV5aO1oHWhpWArcrpV5uyVBNi+j9QO06InID8A4++aIhgna0HnTWdUdgZmAXuoAKHMUTihNKQBFRgcPhBiGW5/BTpaJjmO1ofRj4faKAX4nIvzdJ7D2hFz4hiIRZPBH5ETCDhrSiL1riwMkA3Scu8EMR+U8CIXEiSXhCTtwkxvdL4Fu0OxsnE7Rt/id85yQjIupE2ITNToYm5HsM+CbtzsbJCN1nM/EzzbMAzU3CE6EK28l3asDCJ911wB8JxuObWx03KwGDUIsrIv9CO/lOBdj4ffh3wOOBY2I0JwmbjYCRON+3gQdpH9k4VWDhk/CfROTRIETTbP3aLEyODK9dD/wfDZ5uu8NxaiCaUfNtpdQvm2vE5LgJEiHfJOBdIKe5zv1FhYjgeR5KKQyjzUSsNAkVME0p9VJz5BQeF0m0ay4ivfETHk+jYX5CO44SIoLrulhWmzWbBZ8zVcBZSqmVwUDDMc++O2YCBoaoLqDzLnAO7XbfUUFEUEqFEs80/UeXTqeZOXMmjuMwffp0PM9rS5JQC5iV+MkkFXDs4ZnjuSszYP7P8MmnU+fbcQQQERzHIZPJoJTCNE127tzJww8/zNlnn83NN9/M7Nmzw2PbEAz8vh4J/CYg3jH3+zHJ+khywVfx8/nawy1HAc/zyGQyJBIJAHbs2MFvf/tbnnjiCUpLSwEwDCOUiG0Q2jOeJiLfVkrNOFZ78KhJE0ku6A/8F+0ZzEeMqKpNJBLs3LmTp59+mieeeIKtW7cCEIvFMAyDVCpFXV1dK7f4kNBZND8TkQ+VUh8fCwmPRWqpIF/sCfxKoe1232EQJZ5pmlRVVfH000/z2GOPsXnzZgDi8Tiu64bHAmSz2UOdtrWh8IVPDPitiJwJpI7WKTkqAkZCLt8CptKueg8KTSIdTjFNk0wmwx//+EdmzJjBypUrAbBtG8dxSKfTAI1CL9r2U6rNRrQMfAE0Evg3pdT3AuF0xDhi8kRU71DgAdpz+g4JLc1isRie5/HXv/6VRx99lA8//BAA0zTxPG8/KRd1OFy31aftHgk0Ce8VkVeVUnOPRgoeEQF1yCX4/P+AAhrSq9oRgY7l2bZfF3P27Nk89NBDoUerv2/j6vVoEA3HPRZMuUgfafrWkRJI1xS5Cb9iQbvdx/7hEcdxUEphWRarVq3itttu4+KLL2b27NnYth2q2yMlXxv2gptCS8ExwLcCrhwRtw4rAQOpJyLSCXiIhmj4Fxqu66KUwvM8RATDMLAsi+rqah577DFmzJhBRUUFpmliWdYxSbw2bPsdCDqt/34ReR7YciSq+EhYqk/yPfyhtnbVi08O13XJZrNYloWI8NxzzzFp0iR+/OMfU1FRgWVZeJ4XOiRHc27wPWNoc4Hog0F7xR2ABwP1e9g36JBECmbLeyIyCLibdscjhIiE8bzFixdzxRVXcNNNN7F69Wri8TiGYYQe8LESKD//YKtItFmY+ALqBhE5K3BaD8mXw0qygMk/BPL4AqtfHZ/TToZpmtTV1fHjH/+YCy+8kLfeegvLsjBNk2w2G5JOj/ce7bUAcnNzD3Nkm4UJ/ETXnTnUgQe1AbX+FpEJwM18wbNcRAQRIZVKkUwmKSkp4eabb2bevHmh/ec4zn6/iX4eLYqKio673a0ALQUvBK5QSr1yqBGSIyHU9/FTs7+w0g8IHY5kMsnmzZu5+uqrmTdvHolEAsMw9iPf8V4LoLi4uNnO2cLQPPm+iGjuHBAHJKAWnSIyGriSEzSXV0uVkwGe52HbNrt37+aaa65h2bJlxONxstlss6dL6WfSsWPThZ1OGuiwzGRgaqQy6wEPPCAC2+8e/LE+nQnbrFBKoZQik8k08hY1MdsCObXdp9XvbbfdxooVK4jFYiH5ouO3GoZhhPd3NOTUkjYWi9G5c+fmvp3WwL2HsgX3ezIR6dcPfx2OE1bJYPfu3ZSVlYUZII7jhENY+rO1oEmnlMJxHCzL4tFHH+WNN94gkUjgOE4jcjaFJp9lWUctHUWEHj160K9fP4C2lIx6NNCkmwpMPJgUPNCd6SGU2/CH3Jpd+ukxzqVLl3Luuefy29/+lvLycmKxWDhG6nleq5NQt9W2bT7++GMeeeSRRlkrh4KWZNlsNhx+OxJo+69Hjx5069btqGOIbQgKnzsW/qJCh0dQTEiJSIGIbBIRT0RcaWa4rn/KFStWiG3bAsiAAQPkRz/6kXzyySeSTqcbHe84jjiOI57nNXdTDttOx3Ekk8nI1KlTBZBYLCaWZemStvttSikxTVMA6dKli4wYMUI6dux4wGMPtOnf3nPPPSIiks1mW/y+mxFesFWKSB/NsUMRUBejuSE4gXNCWhU80J07d0q/fv3Chw6IbdtyzjnnyM9+9jP58MMPZd++fY1+qwnhOI64riuu64rneSGpm7ONqVRKREReffVVMU0z3AzDkKDE8H7EMwxDALnwwgvl2muvlU6dOoXHH4x0ep9SSizLEkD+8Ic/iIjs9zKehNAc+n6UYwcjoCG+BHy9yY9PCDKZjIwbNy4kXlPJYlmWDBkyRO6++255/vnnZdOmTfudI5vNSiqVknQ63ewkzGazIiJyzTXXNJJOUdLoLR6Pi1JKbNuWBx98UL7xjW+E96Ol/OEknz6+sLBQ1q5dKyL+C3eSQ3fKEhFJSKBlD0i+4HOQiNSd8FYFZLn66qtDAgJiGIZYliW2bUssFmvUSUVFRXLllVfKAw88IHPnzpVdu3Y1Omc2m202Va3J9/HHH0tOTk4o2Q60aak1YMAAefHFF+XWW2896Et1MAloGEZI8AsvvDCU7lrCn+TQqvjsg0pBaVC/Pwh+dEJfPf1m/9u//VvYiboTtMqybTvcmpJRKSV9+/aV6dOny+9//3tZv379fuc/HomYyWREROR73/teI5IdjHxTp06V1atXy+WXXy6AJBKJRvdzOAkYfQkff/zxsA3NLdVbCZpL/3VAAkqD82GKyEdNfnRiWhQQ8M9//nNo3DdVcVHbSH9qqRI9FpDCwkK54oor5JlnnpGysrLwOtpePBZHpra2VoYPHx62T0sq3bacnBwB5Ktf/ars3LlTrrjiipBIB2r/odSvbdtiGIZ069ZNNm/eLCJyqpBPpEENbxSRfGmqhqVB/Y4UkRaxevXD/eyzz6Rz586NvMcj3fRvmv6uf//+8r3vfU/mz58fXq++vj4k/eE6Vh/33nvvhSpUb1HpDMhdd90l6XQ6lHzJZFJM0zws6aKbYRgSj8cFkPvvv79RG04h6Id+8X5SUESs4PP7wUEtcvdaGl188cWNVNCxbNqDjKrqRCIht956a6iePc8LwxqHkoS68x9++OFQ+kXJov9/7733ikiDk5KXlyfxePyoCagleteuXWXz5s0nxKtvA8gGn7+Kci6UgOKLxbeCg1qEgNrQ/+Uvf3ncBNSqTHuTsVgstL06deokDz30kFRXV4fXPRQBNUEvvPDCRio1Sr5/+qd/EhGRb37zmyHZtSo9mL14sE2fc8aMGSJySko/kQYJuFxE4qLVsAS6WER6iR8wFPE9lhPfouAt37hxoxQVFe0XWzseaRiVLvrvSZMmyZIlS0TEj69pR0XbhlGPs7y8XHr37h2ewzAMSSQSAsjtt98uIiKPP/64QEMI5kidDW062LYtubm5AsiUKVOkrq5OMpnMqeD1HgqOiIzRgi/q/V4XHNCisl9LQR26OFo78GjUMyCdO3eWN998U0R8EmriafLp9nzwwQeN1KmWzn/3d38nIiJz5swJ9x+t5Nbtyc3NFcuypEuXLrJ8+XIRkVOdgFq03xuqYWmw/2aIL/myB/nxCYF+4HPmzAk9weYmoN50PC+ZTMrLL78sIj4Js9lsSEIdfnnyySdD9asJ9uUvf1lqampk586dMnDgwFB9HovpoL3qvLw8eest3/JJpVKtMuTYgtDceiHgnKlDMJaIfBjsbFEDxHEcSaVS4nmeXHnllc0mBQ+kyk3TlEQiIUopyc/Pl1mzZomIhKMojuOEQ18/+MEPBAjV7tixY2XPnj0iInLLLbeEJIp6sEe6aWncqVMnefvtt0VEpK6urpGTdIpCa9dNIpKHhogUi0h1sLNF7z6bzYadPmvWLLEsK/QKj0UaauIZhtFoixJSE7xPnz5SWloaSj4dKxRp8Gxt25aioiJZtGiRiIi88MILoQ13tKEW27ZDsg4aNEg+/NB/5+vr61vykbcFeCIyLkrAyyI7WhRa8ug3/7rrrmskXY5F+unf6WG9A5FFS6G///u/F5EGU0DbhBMnTgxtP62ud+3aJYMGDTrqmKVSqpGUnD59uuzYsUNEfLW7f8jFa/R8TjGJqDXsN6IE/GHwZYvafyINqVZaCi5dulSSyeRBiXO4jtbH67Qpve9Adppt22Kaprzyyiv+zQe2YFVVVTgC8uMf/zhs63e/+12BBq/3SNoTJaoeK9bIZrIHHTLUlDtczPIkhObYf0UJ+PvgyxYPQGnjP0rCb3/7240M9ahqPVIVnJOTI2PHjpVJkyZJfn7+foSIerYTJ06Uurq6UP1+/vnnUlhYKFOnTg095eXLl0uHDh1CE2H/6/pSVxmGmJYpltVAvEQyKd+571uyc8dOERHJZhzJZLOSddPiuEEIyPPEFUfES0uqulwcNyVZ8QKjyRXxPBHP76CMiLiuJ+J64okjrn+EuNIw6u9v+q82Bf22vStBGCYmIgub7GwVuK4r2WxWysrKZNCgQaG9puNwR6uSE4mETJkyRR544AG59dZbQ3LG4/HQ49YknDlzZtiOZcuWyeDBg2Xjxo0i4kuhadOmNVLdui1hTM+yJRbLETsnGV6/U8dC+Yc77pSPV/ghFvFE3HS9SFYk67qSlnrJiieSFclkU5KVGnH2LpPS2f8h2bqNUif1ks464nkZkawjkhGpFZG9niduVkSyjjhenWREgs2TrPgk9cmYDfa0Keg3okREOiIi3URkd5OdrQadBPrKK680suGOhYD6+C5dushPfvITee6552TUqFEhCaMjG1deeWWo6pYsWSKvvfaaiPgvxaJFi8KRDq3m9WiLHSRRqMh1hwwZLD/4/vdkw7rV4X1lsllx6vZJxboXxavd4pPRy0haxCdTKiPiOpJe/rSU/2Gq1K14ScTLiJdKiaeDY1mRrJcWV8olVbpc6nasE0dS4nqe+LRL+5+h4HOkFZTa4aA5lhKRUYjIeGmhBIQjQSaTkbo6Px3xzjvvbGRzHe0oSZRggFxyySUyd+5cueuuu0LpqtV8bm6urFixQkQaAtS1tbUiIvK1r30tlH7RvL3oNqBfP7lt+nR55ZW/SmUkiztbXyPZuhqfQDVbZdu7X5M9cx8Qqd4s4lWL43lS63lSnxHxanZJ9du3S3bmGCl79f8Rb99u8RxPHM/xRZrjiUi5uLtfkd1/ulOqN74uKcmI59aLeGkRLyviOU31cFuFJyJXW8Dp+FMvhTYw8dwwDGzbxvM8HnjgAebNm8eKFSuwbfuoJymJCNlsFqUUsViMt99+m1WrVvHqq68ycuRI/vEf/xHP84jH49TW1vLWW28xcuRIRIR0Ok0ikWDNmjW89NJLYak0z/OwLIs+ffowZMgQvvSlL3HBBRcwctQounbpAvgr/FVkHRKGQY6dg5I0mIKkayjIVkLFfKoXpcg78xrM+FgcUVi2Sf2uuTippVhmDJP5VG5/l8JhX0FcBRhg1pGuXEP9gj9RUL8JLzMaFxBloLDQc8xc/Jl6hvL/3wbn1OkqG6cb+BWv9JetDl3ODKBz584888wzdOrU6Zgmf0tkfnE6nSaZTFJaWsrUqVM566yzeO2110gmk2SzWUzT5L333gvbYJomhmHw7LPPUl1dHdb2u+eee/j444+ZP38+b7/9Ng899BBTp06lY5cupFwH16nBcFLk2BaOaeAoA5QBqh7PEewUFJhVUDGP8kX/i9TtItc1yXHSZDctICebD6nOFGRisPkD1L49mK4NqoJM5WJ2L3yZnPQObGsvqm53sJqghasMXAVZERzJIGTxxJcqbRC6Wf0NoE9rtuRg0POEx44dy69//Wtc1w0nex8rtFSrrKzkoosuYty4cbz11lsUFBTgui4rV65k27Zt4VzeyspK/vSnP6GUIpvNMmjQQB566CHGjh1Lz549/fJsmQxZxyEjgu1WY2ZKMc3dJKQOWzxQghsoFy+bRtwMSJp8K41X9ikVi17AzJbilL+Ct3MBSiBrVaI8k1jNR9RsehFlpXCrVrN38bPk1G7ENj0wFaRqsSWLEVgCyhVsPOKqCtvYi2XUYXptssyv7sQ+BtCzNVtyKOjCjtdffz0//elPyWQyx1U1VJdKSyaT7NixgwsuuIAJEybw+uuv06lTJ7Zv387GjRsBXwq+8847bNy4kUQigeu63HDDjeTn51NTU0M6nUYpA9O0MAxFQgmZ8vXsnv8S6fXvI7Ul5CgDUymUMhFJ4Dp1ZFUFKIGURb6TwSt9h/I1L1BbsReraAr13c6mqngK2aJzUR3Gk/YyOLVb2b3gRXIq5tHBKkeUicTyqa9J4zkOlspguh6GKDAEkQr2lCxkz8aPwEg1V3c0JzQBu1lA1yZftinoieo/+clP2LNnD7/61a8a2YNHYxPqagbZbJZYLMbatWu5+eab+fOf/8xzzz3HlVdeyaJFizjvvPPwPI833ngDAE88cpNJrr7qakSEnJwkhmEgAspQKAVpHGL5Xcip20XmkxXUbFmM2W8oub2GYycmg6HIOOVUSwzbi6PiQ6BbXwp79YROo7DMQRine2A6/pbxiHsmScsiIy6FI67BLOlK/a5PiXtbEZXC8erx6mpQeT1RCkhV4G6ZQ03pR1TuraJo2JdBKVxxQQkKL7AHLXADc6Z1qz12twBdAafNEVCC0reaOL/85S+pqanhmWeeIZFIkMlkjrpygq40kMlksG2bmTNn8sgjj3D//fczY8YMZs+ejYhQU1PDJ598AkA6lWbcmRMZNXIYqDoMA1AWhjLxXQ4XRR4qpzvxThZW3W5i1buoXr2Iyk0F5BReT3JgP6AMo/gSzJ4jsApGYRacjhvEbww8cGpx3FpwBdOMoewYysjBIEu8+ELofiHWvlV4e2ZTXfop6doOmOlKyPGo2/4RmU2zydmznny7FjfWlfxOXcHLQYlAUCrER6t3tW5AgQV0ac2WHA4SVCLV0u7JJ58kHo/zxBNPEI/Hj4mE0FA6w7IsHnzwQc4//3zuvPNORo8eTTqdZtu2bZSWlmKZFo7rMOWs87FiCbLZFLZlghcwJ1gWOa5cMBWprr1hzxzy3Rw6ewZuTS37yl/ByL2EgqHnUtCvGxgFQC2S2oDatYtM5Ubq0tvx6qtw3DpAMA0bK56PiheQY3ZCOp2GdO2P0XkoRucRdOy9j9yqCjy3kr1z/l/c7HySXhYr3g2XOCQSWImekFIYpvK73Aibi5gCeKjWFYEd2vQiM/qN1ZJQFwb/zW9+Q2FhIY888khYfepYa6gopaipqeFb3/oWs2bNYtKkSRiGwcqVK6mqqiIej+O4DiNHjfB/IDbimqhwOW4rcAFSGMRJdLyQvfE3yUt9jkorMuYIOk65HrfPZQg2CiG9eynOjvdxdyzF3rcHw6klbmXAdDFMQAmeI4inUJ5Fxi2gPllIVUFnEt1H0an7eGKdBpNI9sHNdCCvy2SqNu3AtmoxvTgZtw6j8DQk0RFxBWXXBUSzAQOUQoJ/rV1vOSoBW10uHwzaedCE9DyPn//85/Tu3Zv77ruPTCYT1uqLHnckNqKOA86fP5/HHnuM73//+wCUlZWF+5PJJKNGDgXANBR+pC0DBmQljotCxCAmBlaiPxLrT01VBcnCASTGfB+n+yhcgJrV1K59GbVlIclMLZYBWA7EDJSXA8pBXBelBAwTlIGYJuncOmJGDV2qP8fbu4zMhr+Q7jaenGHXYRQOJz767+jQcQB7l/yefHM5YnvEO3bHMYV9hkNSuZgIhoApFuKCMgxEVGvbgKFQbvPQkk5vruty991388YbbzBkyBDS6XSjGKKO4x3peW3b5t///d/ZtGkTANu3bwf8BWUK8vPp3s0PFijHQImJMkwUGWLKIa4UCSOGpWox8mqxOwwi2/lyrIk/RLqPwvP2kbPh99R/+C+Y256h0N6ObcXxjELqbJs6M03GTJMxHLK2kDGFjOGSMbNkzTSWW08yDblOknw3QV5mL+bWD9k357c4W+fiGS5278l0nDyd2rwelGc6YeVPRkkutphYbgGm5GF6CQzPXzbMcF0s1fpd36ZV8MGggrXXHMdh6tSpzJ07l/vuu4/nnnsurOV3JGpZk7S+vh7btnnkkUfo1asXADt37gyPy8svIJGMAfUoS1G1aTnVez8hL6+amBXHVD3xpDsqWYoTUySLzyU+vDeYnTGyu0it/F/s1e9REK+EeC4ZsfFiDp6qAqscw7MRCXzBJgJbIVhZE7BwDBsxY1gqh5xslpzMFio++S+kvpSifjdgdZ5A4YT7yX66HjM2DAOTQrcOUgJeFa6zl3o3Da5BTtHpiOShWlnxnZQE1DBNk1QqRZcuXXj22We55ZZb+MUvfsHf/va3sGazlpgHUsWZTAaA/v3789hjj3H55ZeTTqfxPI+KiorwuA4dCrETObjYmApyCmLUrluFbFsBkkGyhXjkkUmUU5U7guIp15GJx4jJHjKL/pv4Z6+RKcgHKcCQfJSksNmHElD1SVAGrlFDuOqVbqoSFIKoPDwjTSb+OWAi6UJMy8aNV5Jr76Nuxe+orqklf8wtGPmj6T6hP+Xr38NcuwY7uwcjW4vn7iPtZShPxeg08EJyuvdBHIVqAyr4pIVSikQiERazvPjii3nzzTd56623uPHGGykqKsLzvLDyatOtf//+PPjgg3z00UdcfvnljQLdlZWV4XXy8/PJMRIo1yStXKzuY+k87FaUdCYRqyduuyStvZhenG7DL8HLjWNn9sHip/E2vYHXwUJwES+NEhcLEyWW79AQ9x1qIwMqi6gMYjj+pvwxlIydImtlUGKhPAvP8lV01s3Bre9FJ7Mn2ZL/o2bdrzFQeGZHiNeT3vYe8V2LMfYtJ16/Biuziw6detB50Nl4UtDq5IOTXAJqaFvPcRwMw+CSSy7hkksuYfPmzSxdupRPPvmE8vJyMplMSLzJkyczbty4kKQ6Lgi+46GXTwXfmUEpDJVCjDpcsYn1HU+2/EzqtpWRNGNk0y5Wz0nEu58JOKQ2zkKte4tYnkmVEyffC6SZOHgowoUHDBeUAkk00b4KRCEobMmiPMCJ+e1RKV9xuoJIEiebokOuRdm6ORi540n2nUrnfpMo3/oh2co1xK0cBAvX60xh//Mg1hdcCz+HtnVhAXvwF55uE9kwxwO9ZJYuHt6vXz/69evHV77ylQMeL0HhccuyGpXRbbqMajqdxhUXZdjEyfXtJqXIHfllKvatx9y3gfqcPhQOuxLM7mQ+/5ja9X+iIL8Gx7XIlQRIfUAw/YgjnS9G4+901plebNJJAgYKBz/onQWV8f8261BKULUd6Gw7VK79HbGOnbDyxpA7+BL2LtlMkZehOpMgcfokYj0n4Lk2Yvgvg1JHXj74RECX0z+lYJpmuE6vXp0yujmOE24HKiLetLJ9Op0m7WTJolBeHESRVSZOzgjyh99EtduDxIArUB3H4mUqqFvzMgXZzXjiocwcYl4WDhcsl2iUONjwg8WZWC3pWDUpK0vaUqSNJBmKyEgfsl5XMF2wDCxJk5MqoebTDyAtxHucSbzXeCrrTLzCwSQGX4JIVzwMPAFluLR2vowFVALdWrUVzQgVGXI62iUStKPSNH7oZB0cSWOTRdwEihjKUihsrB6TKRyZxe4zBYVNXdk81L4F2Moh6xXh4oFUolQSOZSCUQ1/6EsrZaEErKzCQPlSCxel7UPPRZSi2uuC6SpMEnhmByrL95Go3kIiOYjCfl9m57YyOgw4F5V3Oo5rQOuH/zSqLKA8+M9Jr4KbE9G0r7r6OsgYxHMK/C+8NGb959TXraZqzxY6dBqAyu2IeGWkNs8iz60AIxc8G0Olgqd6iMerBJQTSD0D07AQUegoki0OiId4gqcEN+uCaYJtkbE6kM0dDYVx7GQRuYnTySnshpkbx8NDFQ6n66SbMDsPIOsmwDSwRC9tabZWGEY/jCoLKIt82Q4aRl7033W1dTipKkTtoK5sLd6uHcje5dSzgEryyRv3U19z7l5JvHQztlWAayhMqUbEJKM6YODQ+BFHO95BKRelDBDLP8xRKA88gb1xj4xtY8e7YeYUQ35/cnL7YOYXY+Z0IC9Hga1wKUCRxJJ6lKpHcMFNYnWdSBoLB5M4TpCcYOBitbYXussCdrRuG9o2TNOgLpVm88KnIPdjUnXVFKZzyXOryE/sxc4ZRiI2FkhTv3MxcakDySWrMphGBaaTj0hXlKoA8fyhWBQefooUIngIjgeuq/DEwrDzkJx8YjmFxAq74HQ+g3j+acTz81F2Lhi5uFhkMFGeAA5ZxyCjFAJYEiOuFKYolGmR8SwyBig834HBRSSOar04jF72d7cFbA2+bFe/B4AngpPJYhQWkkwORJVXkDRqMOIVpOlMOtkTq4MHXj3VdZspSGzDdnphkEc6Xk7CrCOeSgcBL4OM4+Ji4GGTFYVt2bg5RbjJ7sTyu0BBH6y8XsTyiyHRBUfFyCEGHniuixIwPBPLUMEp/ZCOaUAibLWBH+bxYYlgBekwnmPhKdsfM8eD1l2FaasFlAT/aSdggGhCAwL19bXUqH4kx19H1p5N+aa3ycXDNWwSiY5g5CLl+7ArXOLkg8TBg6w4IClsr5Z6R+GpBMQ6QW4xZl4f4h1PI57fDZXbCXLyUKYNXgzXs0HF8FIKO+5PKcEAw/AVZm1tLSUlJezbt6/RenQSeP2ZICmjR48eFBcX+8F6N4g3osgG0xus45jecJzQF95kARvxsypbNyDURqEXoN66rQbMYvLGXEWyVx7Va/9CzZ49dM7rC5LArV+PSteQdeI4mTg1dj6ZnIGows4YRYOIF3bDKCjCzuuGkdMF4l3wvFzSrp9aqBTkKFCm718AmBZU7N7Jpq3b2LRlC8uWLmXdunVs2bKFjRs3sm/fvv3aaxgGxcXF9O/fnyuvvJKbbrqJ3NzcJlMZfCLrMFQroBEBtwPVQCfaPeH9oMM4eyorACHl5JLb9Vw6FfQgvXopdB4GBqSNSqpzEhiF40gmh5PsNIgOHQowkz2BbiBGkMMquCKYWBgG5AQa0AW27Sxlw/q1bN28mcWLF7Jx/WeUbNnK5q2lpFKZ/dpmWRZ9+/alf//+jBo1iilTpjB48GD69+8fBtZLSkqYM2cOGzZsYMGCBezcuZNsNsuQIUP4xS9+0exLzR4hFJAhIGA5vh3YTkAaYodaYmhvuLpiFwQjIJlMR2KxifQYPw7Pc8kgJIqG0Oucb2Elc/G8QmJmB1wUKUzEhRyr8cB7dfU+1q75lHVr17B0ySJWfbqejRs3sWXrVlx3/yyemG3T57TTGDp0KMOGDePss89m4MCB9O/fP2zrrl27WLduHXPnzmX+/Pls2LCBbdu2UVJSst/5xo4dSywWC4cvWxCaY3uAbZZSKi0i64CxtIdi8DwP0zRJJpONvt9bvgNw/RFc05+QhGviGULGdbFVV0y7G66Ap4S0J7ji4IhD2smwdMkyVq9czYoVq1ixdBnbSkrZsf1zUs7+ki1u59OlazHDRwxl8NChnDVlPKNGDuX00xsk2549e1i9ejVvv/02H330EevXr2f79u3s3r37gPdVUFDAoEGDGDJkCCNHjmT69Om4rntcswyPEZqAnwGV2gBYG9n5hYaef5ybm9vo+7Id+wADwcHBn4trKxNLmeSZVji0sLe6DhGHgrxcTNNPHsCy2eR6bN24hbLPy7DMBCgTM5Eg7ljkF+QxYsQwhg4ZxtjR45kwYQIDBgwgLz8HgLq6OpYuXcr7789l4cKFrFixgpKSkoOSLZlMUlxczIgRIxg8eDBnnHEGgwYNok+fPuF96VzJ45lnfYzQVRHWKqVcTcBlwedJnZ51tNBDbtHkVd0hhYWFjY7dtacScSFu2cSD77LZNDtKtrFs2XLWrl3G/I8Xs2bNJjw3w2nFPRk+eDh9T+9Pj149GTBwIP/6kweIxXxSVlRWUlFZQXV9LZ06dKRn9+7Ypi/dVn+6kqefeYLFiz9hwYKFbN1aSip14Pm9+fn5FBUVMXLkSAYNGsTIkSMZNWoUvXv3PuCK6+l0Orzno1nHuBmhGb8CGtKxlgMp/FDSF8IOlGBVdp3er6H/7tSpU3gcwK7y3VTuq2THjh0sWrSIxYuXsHDhAjZv3hzOH4liw4YNvPve+1iWycgRvoNw7Veu5YILLvDP37EjhQUF7K2sJB5PIK6EUvT0fgOoGF2JbSfo3r03ZWVllJSUsHnzZlzXZeTIkQwcOJARI0bwpS99iW7dutG1a9f92qAX/tahGqUU8Xh8v+NaGFrILQawxF8npBRYDYynIUp9ykMpFU5w1/VgtE3Us6c/B0QTcPPmzZx33nls3bqVqqqqA57Psky6devOqFGjOOOMM5g4cSKTp0ymsMCXpvv27WP+/PksWbKEpUuXsnDhQnbs2EF+QT49e/Skb9++dO/ene7duzNhwgRuu+1W4vGG8HJ1dTWu69KhQ4dG19XpY9qjNU2z0RyaNgQt3EoJzD4LMJVSWRH5GBjHKW4HasnXlHCO41BSUsKSJUtYuHAhr7/+eni8aZrU19ezcuXKRueKx+MUFxczfvx4n2yTJzN27FgSCZ80lZWVfLzw47DC15IlS9i9e/d+6rS8vJwtm7ewdOlSBgwYwDnnnEOvXr2orq4JCVhRUUFtbS0Ae/fuJTc3l6Kiov2I1iiI3vbg4nNukVJqr4gYFg2Emwf8E6ewHag7Rwdft2/fzpIlS3j//fdZvHgxq1atory8PDxeS0iNWCxG7969OeOMMzjnnHOYPHkyI0eODPeXlJQwc+ZM5s+fz9KlS/n000/Zu3fvAdti2zY9evRg+PDhnHfeeUyYMIFJkyaF5K2urmb58uV88MEHrFq1io8//pg9e/aEhMvPz6dv374UFxfTq1cvpkyZwnnnnUdeXl5bJyHAguCzEQE/AmqAPE5BO1BnSi9evJjnn3+eBQsWsGzZsnBi0oFgmia9e/dmzJgxXHrppUycOJExY8YAUFNTw4YNG3j00UdZvHgxy5cvZ+vWrdTX1x/wXDk5OfTr148xY8Zw1lln8aUvfYmxY8eGL8POnTt57733eOedd1i9ejWrVq1i165dB53ZV1VVhVKKwsJCOnToEBJXOxhtFCY+t94L/u/pdeL0PP93gfPwReUpZwdqNbpu3ToqKirYunUr69ato6ysjJ07d1JWVka3bt0YPXo05557LhMmTODMM88MvcWVK1fy5ptv8sEHH7BkyRJ27Nhx0InvlmXRr18/Ro0axSWXXMIZZ5zBqFGjwv0bNmxg/vz5zJo1i08//ZS1a9dSU1Nz0LZ37tyZAQMGMG7cOM4880xGjx7NsGHD9vNkW2lk40gQhl+ALymlakVEaQJaSilHRH4K/IRTlIAHQyqVoqysjKqqKoqLi8MQjOu6vPjiizz//PMsWrSIzz///JDn6d27N6NHj+biiy/mrLPOYuzYseG+devWMX/+fGbPns2yZctYt25dI+kbzUEEn3DDhg1jwoQJnHHGGYwZM4bTTz+90ditrv6qpaQmXiuN7x4ODj6nnlJK/YOImEopN5SASilPRCYA8wknJ5zc0GEWaPBmdfkO8G26qLQoKSnBsiy6du2KZVk4jsPatWvZvXs3ZWVloaQqKytj8+bN7N27N3QaLrjggrBwJcBnn33GkiVLePPNN1m6dClr165tNNNOn19DKcXQoUOZOHEiF198MePHj2fQoEGN7ida8RUaCBctRRL9fxuDloDXKqVebkpA3WIb30AcG/nBSYum8T2lVCOVtXfvXpYuXcrcuXN59913WbVqFclkMgyHDB8+nHHjxtGtWzc6duzIgAEDQuKUl5eTzWYpLi4Oz7dz507+53/+h9dee40lS5Y0uj74NmX0O21fnnXWWUyaNInRo0dTUFAQ7heRRgHyNqpajwTR8MtIpVSliCilVEi8qBp+APgxJ7ka1uEWEWlEum3btvH+++/zzjvvsGDBAjZs2BDu0yWAmxKnc+fOXH311dx5552MHz8e8MM2K1euJJlM0rNnT3JzczEMg6qqKsrLy6msrGTVqlWsWLGC7du3s2HDBkpLSxk5ciQTJ07k/PPPZ9iwYaHE1G12HCckW3SC1UkOF1+Y/a9S6jatcSGiZiNqeCR+lNriJFTDugOjg+xbtmzhvffe47XXXuOjjz5qVPfFsqyw/mDUJhs4cCAXXHAB11xzDeeeey45OTlhIPlvf/sb7777LmvWrCE/P58ePXrQvXt3hg4dypgxYygqKqJ79+6MGDEiHHtNpVLU19fTsWNHoqirqwsJF50ieooQT0NLwEuVUm9r9QuNCaj/NmjwhtucGo5OndSGu1ZTegQAYOvWrcyZM4eZM2eyYMGCRsNlsVgs/G2UdKeddhqXXnopN9xwA+eeey5KKSorK5k1axavvfYa8+bNC2tIR68XteUAevXqxWWXXcZdd90Vhm0qKipYvnw5sViM/v37U1BQsF/GDdBaGSonEppD6/BH2uoAgjVfGiZFKaVEM1NE/ohPwDY3KqJVq1aVlmWFXt+uXbuYPXs2r776KrNnz2bXrl3h72zbDqVLtKpqcXExF154IdOmTeOiiy7Ctm22bdvG7373O15++WUWLlzInj17wvNYlkUsFsN13dCpMAyDYcOGcdlll3HttdcyadKksD3PP/8877zzDrNnz2br1q3EYjG6d+9O586dGTJkCP379w8l5rhx4xgwYEBbDqUcCzSHXghCL6H02//IQAqKSJGIlEobW2tHL+isFxUU8Vc1euedd+SOO+6QPn36NFq9SK9mrlfF1N8XFhbKVVddJS+88EK4QGJJSYk8/vjjcvbZZ0tubu5+50kmk41WXQJk4MCBcu+994br/oqIlJaWypNPPinXXXed9OjR44DtiX4H/rrFd9xxh3zwwQfhwo2nCDR/akRkUMCtQ79ZImIGnzOCk7SZpxFd1vSzzz6T//zP/5TJkyc3Wr0yFotJIpEIFySMdvSZZ54pjz32mOzatUtERCorK+Wpp56SSy+9VHJycsLj9EqaiUQiXDFdb71795ZvfOMb4WrrIiK7d++WJ598Uq666iopLCwMj9VLheXk5DR6AQzDkLFjx8qPfvQjmTNnTrg0WdN7PAWgufPnIyJf9CARGS7+4oxtQgrqhQS3b98u999/v/Tt23c/SaK3KCG7dOki3/jGN2ThwoXhuV5//XWZNm2adOrUaT8JpZdjjZ6jY8eOcu211zaSmJWVlfL000/LVVddJR07dmxE3lgsJvF4vBGpDcOQ4cOHy3333bcf6UTkoOsGn8SIrlY3NSrcojigqyUNHvGLwDTaUEimrq6OHTt2UF1dzdatW9m2bRsbNmxgzZo1lJaWUlFRwZ49exg6dCi33HILX/3qV+nbty8lJSU899xzPPfccyxfvhwgjAtqJ8a27UZjuRMnTuTGG2/khhtuoHv37riuy+uvv87zzz/PrFmzGmUkaxtTOyXaMenTpw+XX3451113HZMmTQodDwkcIF2l9RSy+TQ0Z+YB5wOudjwOC2mQglOkDa27eDj7qLq6WtatWyfvv/++1NfXi4gvqe6//34pLi4+qMSMqsdkMinTpk2T2bNnh+ddvHix3HPPPftJXW1f2rYt8Xi8kSQ9//zz5cknn5TPP/+8URszmYxkMplQop9iq6FHoTtqWsClAwqwgwabpEFfvwlcTBuQghKEXCQIwehsXwk8Wh1wdhyHHTt20LNnzzCXb9++fWFW8aJFi1izZg2ff/45paWl7N69m65du3LTTTcxffp0xo4dS21tLX/5y1945pln+OCDD8Jwjfa49eQlXZ0V/PDLddddx4033sjEiRNDqaZrDTbN2zsFpZ6GDr2sBCYCaWgIvURxKALqkMz5wCzaSKa0BGOhOgzjOE6YilRWVsazzz7Lk08+SXV1NYMGDaJnz54MHz6c0aNH07t3bwYMGBCqwVQqxbZt29i8eTNDhw6ld+/eADz99NPMmDFjvwRUDR241qp71KhR3H777UybNi0c2dDp8NHY5BcIWlhNV0r9Xg4Rejnkk5EGW/Al4FpaWQpqiac7Nzr5+umnn+app5464BxYDdM06dChA126dOErX/kK//zP/xyOVFRVVZFIJIjFYtTX11NWVkZ5eTmbNm1i4cKFrF+/nl27dvHZZ5+xZ88eLMvi/PPP5+tf/zqXXXYZBQUFoV2nbcsvIPGggSMLgbPxbb+DLldwOAJqKTgOP0nBJCzl3vKQYKxUE2/jxo387ne/46mnngqDznqUQ6tFrfZ0GnyfPn24++67ueOOO0gmk7z55ps8/vjjbNiwgZ49/XkZo0aNYvDgwZx22mkMHDiQ/Px8wJ9RVlpayvbt27Esi0mTJoUvhHY6tFPxBSUfNBDwCqXU64eSfkcEaYgL/qaJcdmiiDof27dvl+9+97tSVFQUGv7xeFxM05TAzhDDMBqFUk477TSZMWNGeJ6ZM2fK2WeffVDHhCCc06NHD+nfv79cccUVsmzZskZtymazks1mwwC5DqOcwo7F4aA76bUod44LImKIiBKRniKyW0TcYGsRZDKZMPZWXV0tjz/+eCNv1LKsRqQzTVMSiUTo2RYVFcmPfvQjqampERGRV155RSZOnNgoPmeappimKbZti2VZkkgkJJlMhsdcddVV8sYbb0htbW3oxZ5CoxXNCVdE6kVkdLMRMHoiEbknuFCLPP1oYPb111+X8ePHh6SIkkxvtm2Hw2iWZckdd9whpaWlIiIyb948ufTSSxsdG/29Hv2IDrdddNFFjcIxuk1a6rWjETQnfq4FV7OQLziZEhFTRGIi8lFwoRMqBT3PE9d1ZcmSJfK1r30tVKc67mYYRij5CGJ5euht1KhRMmfOHBERWbNmjUybNi0km5Z2hmHsR1799+jRo+XFF18MSZZKpSSVSoWjFafgqMXxwhU/TvyZiHSQQGs2GwEDEurg9EQRSYnP+BMmBnQHP/zwwyExcnNzxbKsUFUahiGGYYTjtfF4XH74wx+G5P3Xf/1Xyc/PD4mn7URNXqVUeA6CpID/+I//kKqqKhHx7c5sNtuoTZ7ntUu/xvCkQfpdHXDkxERKpEEVPxBc8ISqYt3RCxYskPPOO68REfW4rZZcY8eOlfnz54uIyGuvvSajR49uJN2ihNOf0USDu+66S0pKSkSkYbSiHUcEzYGnTyj5gpMr8cVrQkQWNWlAs8PzvJAImUxG/vu//1sGDRoU2myaPF//+tclnU5LTU2N3H777Y2GxDTx9HdKKbEsK7T1+vbtKy+99FJ4vaiqbcdhoR/SVhHpIj43TuzwjjSo4jEiUicN+r/Z4XmeOI4jmUwmJMSePXvkoYceki5dukj37t3l//7v/0RE5P3335chQ4YIIDk5OQd0UmjiNV9//fWybds2ERGpr6+XdDodOhntXu4RQT+kSwNOtMwghTSo4juDBmQP2LzjRNTe0rE2jfXr18u6detEROQ73/lOo2QCrZ61w6HTq7S6zs3NlV//+tfhuaLnbbfvjhiafA+1KPkiJLSCz983adAJhZaKGpWVlfKLX/xCzjjjjEaq9mDb8OHDwwzmdlV7zNAdMFv86Igpx+j1HrOrHLlgAfA+MJoWnMSkEwEkqF6VzWaZO3cuf/3rX1m/fn24cib4eX+ZTIZ+/frx4IMP0rVr13B51i/wkNmxQvdxCXC2UqpEItMsjxbH9fSlIVlhKH5xow608Ew6CSYpHU05ilNw5llLQWsSB7hYKfW+HOdY73G//tKQsHAV8FLwdYuX9pAmVQQOdswXPFHgeCA01Pf7R6XUE8dLPmgmkkhDVYW7gf+kYSZ8e0+fOnDwyfewUuqfdZ8f70mbjSAREj4M/ICGBrfj5Ifuyz8opf5efI/XO+I5HodAcxJQAUagjn8F3EU7CU8F6GXc/gLcgN+n0hzkg2ZWkQEJ9Tmfx59R174O3ckLLUDmAlcqpaokqGrVXBdoVm+1SRzuFmAmPvmO21ZoR4tDk+8D/Jp+VUHUo9nIBycgXKIbqJTKADcBf8a/kXYSnjyIku9qpVTF8cT6DoUTEq8LCh0pfPV7E/Ab/Btyoe0VPGpHCB3js4CX8dVu5YkiH5zAgHFEVDtKqTuBR2iokn5CbqYdxwXdLxbwe+B6pdS+E0k+OMEjFpqEQcDy+8C9wTUN2knYluDhO48m8JBSarpSKnOiyQctFChuEqK5DvgdUEgbqLbQjrAPMsA9Sqn/ET/lrtlCLYdCSw+X6WD1GOB/gVE0lO9vHzVpeWjylQC3K6VmNWeQ+UjQosVJAvJZSqll+BWTXqChFvVxjSm246jg0VBqZRZ+VsusoG+OvIpVM6DFq+MEJDSUUhVKqRuA+/CXijVpJ2FLQI/TG8BDwCVBSpXZHGO7R4tWU3t61CRI55qMH6oZRYM31m4bNi88/GdrApuAbyqlXoeGtLrWaFSr1QcLJgt5gdj/CJiCH6rRD6k9Ztg80GlUBsFSWcBkXbclGFprtYhEmzD8o3ll4peD+zkwIdjdntBw7IhGGdYC/6yU+gs0fuatiTZBQNgvVJMAvgN8F+hIu1o+WmiJZuCHV34JPKKUKm9pL/dwaDME1GgiDQcD/wLcjN/W6INtx/6I2nkAfwUeVEothrYj9aJocwSExtIw+P85+EmulwWHNH3QX3Q0fR4fAD+POBltSupF0SYJqBFE5NFGsvi1R74DnKMPoWESVJu+lxOAA937UuAx/Mxlt+nza4s4KTot+gYH0vEy/IzrS2h46138+znV1fOBpP9c4NfAX5VSKWib6vZAOCkIqNFUlYjIJOAfgKuBzsFhuoNOJTJqaRe9p2rgLeB/lFLvhgeeJMTTOKkIqBEQUSKq+TT8+QpfBcZFDj2ZyaiHy/SohcYa4E/AH5VS66HBZqaN2nmHwklJQI3AxlERZyUGnIk/F+ViYFCTn2jJ0BZtxmieZNP2bQVmAy8CHyilamH/+z8Z0dY64ZhwoI4QkUJ8Ml6JP8oyiv2loB5tiXZ4SzwTPW8mmofXFGvwq028jk+6cM3YphrgZMYpQUCNiCpS0YH1ILA9FDgXmIy/cPLphzhVVHXDsS1NIZFPfa5DnWc7/kr1C4A5wCqlVE3kHjRJTzo1eyicUgSM4mBkDPYVAP3xh/tGA4OBgUA3IH6Cm5YByoH1wAZgGbAIWKeU2tuknRaBpDyVSBfFKUvAKCLzlXWmr3uA/YVAH3zJ2A+foH3wSdk92F94hJesBvYCu4Fd+Amfm4Jtc/D/iqYqNJByesSnRTKSWxv/P1YRVA4zoRC0AAAAAElFTkSuQmCC" alt="Grand Elevation Solar" width="42" height="42" style="border-radius:50%; display:block; margin:0 auto 14px;">
                  <h1 style="margin:0; font-family:'Sora', Arial, Helvetica, sans-serif; font-size:20px; font-weight:700; color:#0A0A0A; letter-spacing:-0.01em;">Reset your password</h1>
                </td>
              </tr>

              <!-- Body -->
              <tr>
                <td style="padding:32px 36px;">
                  <p style="margin:0 0 16px; font-family:'Inter', Arial, Helvetica, sans-serif; font-size:15px; color:#444; line-height:1.6;">
                    We received a request to reset the password for your account. Click the button below to choose a new one.
                  </p>
                  
                  <p style="margin:0 0 28px; font-family:'Inter', Arial, Helvetica, sans-serif; font-size:15px; color:#444; line-height:1.6;">
                    This link expires in <strong style="color:#0A0A0A;">1 hour</strong> and can only be used once.
                  </p>

                  <!-- CTA -->
                  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                    <tr>
                      <td align="center" style="padding:0 0 28px;">
                        <a href="{reset_link}" style="display:inline-block; background-color:#0A0A0A; color:#FAF8F3; font-family:'Inter', Arial, Helvetica, sans-serif; font-size:15px; font-weight:600; text-decoration:none; padding:14px 32px; border-radius:999px;">
                          Reset password
                        </a>
                      </td>
                    </tr>
                  </table>

                  <p style="margin:0 0 12px; font-family:'Inter', Arial, Helvetica, sans-serif; font-size:13px; color:#6B6B6B; line-height:1.5;">
                    If the button doesn't work, paste this link into your browser:
                  </p>
                  <p style="margin:0; font-family:'Inter', Arial, Helvetica, sans-serif; font-size:12px; color:#6B6B6B; line-height:1.5; word-break:break-all;">
                    <a href="{reset_link}" style="color:#E8651C; text-decoration:underline;">{reset_link}</a>
                  </p>
                </td>
              </tr>

              <!-- Footer -->
              <tr>
                <td style="padding:24px 36px; background:#FAF8F3; text-align:center; border-top:1px solid rgba(10,10,10,0.06);">
                  <p style="margin:0 0 6px; font-family:'Inter', Arial, Helvetica, sans-serif; font-size:12px; color:#9B9B9B; line-height:1.5;">
                    Didn't request this? You can safely ignore this email.
                  </p>
                  <p style="margin:0; font-family:'Inter', Arial, Helvetica, sans-serif; font-size:12px; color:#9B9B9B; line-height:1.5;">
                    &copy; 2026 Grand Elevation Solar
                  </p>
                </td>
              </tr>

            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
    """
    message.attach(MIMEText(html_content, "html"))

    # Base64url encode parameters for API transit standard
    raw_base64 = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    # Perform blocking API request
    return (
        service.users().messages().send(userId="me", body={"raw": raw_base64}).execute()
    )


async def authenticate(
    request: FastAPIRequest,
    session: AsyncSession,
) -> Users | None:
    token = request.cookies.get("session_token")

    if token is None:
        return None

    statement = select(Session).where(Session.token == token)
    result = await session.exec(statement)
    db_session = result.first()

    if db_session is None:
        return None

    if db_session.expires_at < datetime.utcnow():
        await session.delete(db_session)
        await session.commit()
        return None

    statement = select(Users).where(Users.id == db_session.user_id)
    result = await session.exec(statement)
    user = result.first()

    if user is None:
        await session.delete(db_session)
        await session.commit()
        return None

    return user
