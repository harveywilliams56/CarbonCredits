from setuptools import setup, find_packages

setup(name='TISTpolygons', version='1.0', packages=find_packages(),
      
      # this will return every module listed in requirements.txt
    install_requires=[line.strip() for line in open("requirements.txt", "r").readlines()],
      
      )
